"""Injected real and fake hardware drivers for physical chess movement."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from time import sleep
from typing import Protocol

from physical_config import (
    DIR1_PIN,
    DIR1_START_STATE,
    DIR2_PIN,
    DIR2_START_STATE,
    MAGNET_PIN,
    MAGNET_START_STATE,
    MOVE_SETTLE_TIME,
    STEP1_PIN,
    STEP1_START_STATE,
    STEP2_PIN,
    STEP2_START_STATE,
    STEP_HIGH_TIME,
    STEP_LOW_TIME,
)
from physical_geometry import Point, Segment, segment_motor_steps


class HardwareError(RuntimeError):
    pass


def force_gpio_output_low_with_pinctrl() -> None:
    """Keep motor and magnet pins output-low after gpiozero releases them."""
    pins = [DIR1_PIN, STEP1_PIN, DIR2_PIN, STEP2_PIN, MAGNET_PIN]
    for pin in pins:
        subprocess.run(
            ["pinctrl", "set", str(pin), "op", "dl"],
            check=False,
        )


class HardwareDriver(Protocol):
    def move(self, segment: Segment) -> None: ...
    def magnet_on(self) -> None: ...
    def magnet_off(self) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class HardwareCommand:
    name: str
    value: object | None = None


class FakeHardwareDriver:
    """Records commands without importing gpiozero or touching hardware."""

    def __init__(self, *, fail_at_command: int | None = None) -> None:
        self.commands: list[HardwareCommand] = []
        self.fail_at_command = fail_at_command
        self.magnet_is_on = False

    def _record(self, command: HardwareCommand) -> None:
        self.commands.append(command)
        if self.fail_at_command == len(self.commands):
            raise HardwareError(f"Injected failure at command {len(self.commands)}: {command.name}")

    def move(self, segment: Segment) -> None:
        self._record(HardwareCommand("move", segment))

    def magnet_on(self) -> None:
        self._record(HardwareCommand("magnet_on"))
        self.magnet_is_on = True

    def magnet_off(self) -> None:
        # Record every safety-off attempt, even when the magnet is already off.
        self.commands.append(HardwareCommand("magnet_off"))
        self.magnet_is_on = False

    def close(self) -> None:
        self.magnet_off()
        self.commands.append(HardwareCommand("close"))


class GpioHardwareDriver:
    """gpiozero driver. GPIO is initialized only when this class is constructed."""

    def __init__(self) -> None:
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:
            raise HardwareError("gpiozero is required for real hardware") from exc

        devices = []
        try:
            self._dir1 = OutputDevice(DIR1_PIN, initial_value=DIR1_START_STATE)
            devices.append(self._dir1)
            self._step1 = OutputDevice(STEP1_PIN, initial_value=STEP1_START_STATE)
            devices.append(self._step1)
            self._dir2 = OutputDevice(DIR2_PIN, initial_value=DIR2_START_STATE)
            devices.append(self._dir2)
            self._step2 = OutputDevice(STEP2_PIN, initial_value=STEP2_START_STATE)
            devices.append(self._step2)
            self._magnet = OutputDevice(MAGNET_PIN, initial_value=MAGNET_START_STATE)
            devices.append(self._magnet)
        except BaseException:
            for device in reversed(devices):
                try:
                    device.off()
                    device.close()
                except Exception:
                    pass
            if devices:
                try:
                    force_gpio_output_low_with_pinctrl()
                except Exception:
                    pass
            raise
        self._closed = False

    def _set_direction(self, segment: Segment) -> None:
        if segment.axis == "vertical" and segment.end.y2 > segment.start.y2:
            self._dir2.on()
            self._dir1.off()
        elif segment.axis == "vertical":
            self._dir2.off()
            self._dir1.on()
        elif segment.end.x2 > segment.start.x2:
            self._dir2.off()
            self._dir1.off()
        else:
            self._dir2.on()
            self._dir1.on()

    def move(self, segment: Segment) -> None:
        step_count = segment_motor_steps(segment)
        if step_count <= 0:
            raise HardwareError(f"Movement has no calibrated steps: {segment}")
        self._set_direction(segment)
        try:
            for _ in range(step_count):
                self._step1.on()
                self._step2.on()
                sleep(STEP_HIGH_TIME)
                self._step1.off()
                self._step2.off()
                sleep(STEP_LOW_TIME)
        except BaseException:
            self._step1.off()
            self._step2.off()
            raise
        sleep(MOVE_SETTLE_TIME)

    def magnet_on(self) -> None:
        self._magnet.on()

    def magnet_off(self) -> None:
        self._magnet.off()

    def close(self) -> None:
        if self._closed:
            return

        close_error = None
        try:
            self._step1.off()
            self._step2.off()
            self._magnet.off()
            sleep(0.02)

            self._dir1.value = DIR1_START_STATE
            self._step1.value = STEP1_START_STATE
            self._dir2.value = DIR2_START_STATE
            self._step2.value = STEP2_START_STATE
            self._magnet.value = MAGNET_START_STATE
            sleep(0.05)
        except Exception as exc:
            close_error = exc
        finally:
            for device in (
                self._step1,
                self._step2,
                self._dir1,
                self._dir2,
                self._magnet,
            ):
                try:
                    device.close()
                except Exception as exc:
                    if close_error is None:
                        close_error = exc

            try:
                force_gpio_output_low_with_pinctrl()
            except Exception as exc:
                if close_error is None:
                    close_error = exc
            self._closed = True

        if close_error is not None:
            raise HardwareError("Could not completely reset GPIO pins") from close_error
