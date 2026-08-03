from gpiozero import OutputDevice
from time import sleep
from evdev import InputDevice, ecodes, list_devices
import select
import subprocess

# ============================================================
# USER CALIBRATION VALUES
# ============================================================

# Measure one physical chessboard square and enter its width here.
SQUARE_SIZE_CM = 7.0

# Start with conservative values, run one-square tests, measure the
# actual travel, and then replace these values using:
#
# new_steps = old_steps * SQUARE_SIZE_CM / measured_distance_cm
#
# Horizontal and vertical are separate in case the mechanism behaves
# slightly differently on the two axes.
HORIZONTAL_STEPS_PER_SQUARE = 352
VERTICAL_STEPS_PER_SQUARE = 355

# These values control speed, not movement distance.
# They match the approximate stepping rhythm of motor_and_magnet.py.
STEP_HIGH_TIME = 0.0017
STEP_LOW_TIME = 0.0002

# Pause after each completed movement.
MOVE_SETTLE_TIME = 0.10

# ============================================================
# GPIO PIN CONFIGURATION - BCM numbering
# ============================================================

DIR1_PIN = 20
STEP1_PIN = 21

DIR2_PIN = 23
STEP2_PIN = 24

MAGNET_PIN = 17

DIR1_START_STATE = False
STEP1_START_STATE = False
DIR2_START_STATE = False
STEP2_START_STATE = False
MAGNET_START_STATE = False


dir1 = OutputDevice(DIR1_PIN, initial_value=DIR1_START_STATE)
step1 = OutputDevice(STEP1_PIN, initial_value=STEP1_START_STATE)

dir2 = OutputDevice(DIR2_PIN, initial_value=DIR2_START_STATE)
step2 = OutputDevice(STEP2_PIN, initial_value=STEP2_START_STATE)

magnet = OutputDevice(MAGNET_PIN, initial_value=MAGNET_START_STATE)


# ============================================================
# CLEANUP
# ============================================================

def force_gpio_output_low_with_pinctrl():
    """Force all motor and magnet pins to output-low after gpiozero closes."""
    pins = [DIR1_PIN, STEP1_PIN, DIR2_PIN, STEP2_PIN, MAGNET_PIN]

    for pin in pins:
        subprocess.run(
            ["pinctrl", "set", str(pin), "op", "dl"],
            check=False,
        )


def reset_pins_to_start_state():
    """Stop pulses, turn off the magnet, and restore startup states."""
    step1.off()
    step2.off()
    magnet.off()
    sleep(0.02)

    dir1.value = DIR1_START_STATE
    step1.value = STEP1_START_STATE
    dir2.value = DIR2_START_STATE
    step2.value = STEP2_START_STATE
    magnet.value = MAGNET_START_STATE

    sleep(0.05)


def cleanup_gpio():
    print("\nResetting GPIO pins...")

    reset_pins_to_start_state()

    step1.close()
    step2.close()
    dir1.close()
    dir2.close()
    magnet.close()

    force_gpio_output_low_with_pinctrl()
    print("GPIO pins forced to output-low.")


# ============================================================
# KEYBOARD
# ============================================================

def find_keyboard():
    devices = [InputDevice(path) for path in list_devices()]

    if not devices:
        raise RuntimeError("No evdev input devices were found.")

    print("Available input devices:")
    for index, device in enumerate(devices):
        print(f"{index}: {device.path} - {device.name}")

    while True:
        choice = input("\nChoose keyboard device number: ").strip()

        try:
            return devices[int(choice)]
        except (ValueError, IndexError):
            print("Invalid device number. Try again.")


def discard_pending_keyboard_events(keyboard):
    """Discard releases or repeated keys that accumulated during a move."""
    while True:
        readable, _, _ = select.select([keyboard], [], [], 0)
        if keyboard not in readable:
            return

        try:
            keyboard.read()
        except BlockingIOError:
            return


def check_stop_key_during_move(keyboard):
    """
    Return:
        'stop' when SPACE is pressed,
        'quit' when Q is pressed,
        None otherwise.
    """
    readable, _, _ = select.select([keyboard], [], [], 0)
    if keyboard not in readable:
        return None

    try:
        events = keyboard.read()
    except BlockingIOError:
        return None

    for event in events:
        if event.type != ecodes.EV_KEY or event.value != 1:
            continue

        if event.code == ecodes.KEY_SPACE:
            return "stop"

        if event.code == ecodes.KEY_Q:
            return "quit"

    return None


# ============================================================
# MOTOR DIRECTIONS
# These direction combinations are copied from motor_and_magnet.py.
# ============================================================

def set_direction_up():
    # UP = motor 2 RA + motor 1 A
    dir2.on()
    dir1.off()


def set_direction_down():
    # DOWN = motor 2 LA + motor 1 D
    dir2.off()
    dir1.on()


def set_direction_right():
    # RIGHT = motor 2 LA + motor 1 A
    dir2.off()
    dir1.off()


def set_direction_left():
    # LEFT = motor 2 RA + motor 1 D
    dir2.on()
    dir1.on()


DIRECTION_FUNCTIONS = {
    "UP": set_direction_up,
    "DOWN": set_direction_down,
    "RIGHT": set_direction_right,
    "LEFT": set_direction_left,
}


# ============================================================
# MOVEMENT
# ============================================================

def pulse_both_motors(step_count, keyboard):
    """
    Pulse both motors synchronously for an exact number of steps.

    Returns:
        'complete', 'stop', or 'quit'
    """
    for current_step in range(step_count):
        # Poll every 10 steps so SPACE/Q can interrupt a long movement.
        if current_step % 10 == 0:
            stop_request = check_stop_key_during_move(keyboard)
            if stop_request is not None:
                step1.off()
                step2.off()
                return stop_request

        step1.on()
        step2.on()
        sleep(STEP_HIGH_TIME)

        step1.off()
        step2.off()
        sleep(STEP_LOW_TIME)

    return "complete"


def move_one_square(direction, keyboard):
    direction = direction.upper()

    if direction in ("UP", "DOWN"):
        step_count = VERTICAL_STEPS_PER_SQUARE
    elif direction in ("LEFT", "RIGHT"):
        step_count = HORIZONTAL_STEPS_PER_SQUARE
    else:
        raise ValueError(f"Unknown movement direction: {direction}")

    if step_count <= 0:
        raise ValueError("Steps per square must be greater than zero.")

    DIRECTION_FUNCTIONS[direction]()

    print(
        f"Moving {direction}: {step_count} steps "
        f"(target distance {SQUARE_SIZE_CM:.3f} cm)"
    )

    result = pulse_both_motors(step_count, keyboard)

    step1.off()
    step2.off()
    sleep(MOVE_SETTLE_TIME)

    if result == "complete":
        print(f"{direction} movement complete.")
    elif result == "stop":
        print(f"{direction} movement stopped with SPACE.")

    # Remove key releases and auto-repeat events generated during movement.
    discard_pending_keyboard_events(keyboard)
    return result


# ============================================================
# MAGNET AND CALIBRATION INFORMATION
# ============================================================

def toggle_magnet():
    magnet.toggle()

    if magnet.value:
        print("M - Magnet ON")
    else:
        print("M - Magnet OFF")


def print_calibration_values():
    horizontal_steps_per_cm = HORIZONTAL_STEPS_PER_SQUARE / SQUARE_SIZE_CM
    vertical_steps_per_cm = VERTICAL_STEPS_PER_SQUARE / SQUARE_SIZE_CM

    print("\nCurrent calibration:")
    print(f"Square size:                 {SQUARE_SIZE_CM:.3f} cm")
    print(f"Horizontal steps/square:     {HORIZONTAL_STEPS_PER_SQUARE}")
    print(f"Vertical steps/square:       {VERTICAL_STEPS_PER_SQUARE}")
    print(f"Horizontal steps/cm:         {horizontal_steps_per_cm:.3f}")
    print(f"Vertical steps/cm:           {vertical_steps_per_cm:.3f}")
    print(f"Step high time:              {STEP_HIGH_TIME:.6f} s")
    print(f"Step low time:               {STEP_LOW_TIME:.6f} s")


def print_controls():
    print("\nControls:")
    print("UP ARROW     = move exactly one vertical square up")
    print("DOWN ARROW   = move exactly one vertical square down")
    print("RIGHT ARROW  = move exactly one horizontal square right")
    print("LEFT ARROW   = move exactly one horizontal square left")
    print("M            = toggle magnet")
    print("P            = print calibration values")
    print("SPACE        = stop the current movement")
    print("Q            = quit")
    print("Ctrl+C       = emergency quit")
    print()
    print("Each arrow movement starts only on a new key press.")
    print("Holding an arrow does not intentionally command repeated squares.")


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    keyboard = find_keyboard()

    print_controls()
    print_calibration_values()

    running = True

    while running:
        readable, _, _ = select.select([keyboard], [], [], 0.1)
        if keyboard not in readable:
            continue

        try:
            events = keyboard.read()
        except BlockingIOError:
            continue

        for event in events:
            if event.type != ecodes.EV_KEY:
                continue

            # 0 = released, 1 = pressed, 2 = held/repeated.
            # Only value 1 starts a movement.
            if event.value != 1:
                continue

            if event.code == ecodes.KEY_UP:
                result = move_one_square("UP", keyboard)

            elif event.code == ecodes.KEY_DOWN:
                result = move_one_square("DOWN", keyboard)

            elif event.code == ecodes.KEY_RIGHT:
                result = move_one_square("RIGHT", keyboard)

            elif event.code == ecodes.KEY_LEFT:
                result = move_one_square("LEFT", keyboard)

            elif event.code == ecodes.KEY_M:
                toggle_magnet()
                result = None

            elif event.code == ecodes.KEY_P:
                print_calibration_values()
                result = None

            elif event.code == ecodes.KEY_Q:
                running = False
                break

            else:
                result = None

            if result == "quit":
                running = False
                break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCtrl+C detected.")
    finally:
        cleanup_gpio()
