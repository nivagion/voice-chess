# Physical movement tuning notes

## Magnet pickup delay

After the carriage reaches a piece's square center, the executor turns on the
electromagnet and waits **50 ms** before starting to carry the piece. This happens
for every pickup, including a captured piece taken to the graveyard and the
attacking piece moved afterward. The delay gives the magnet time to grip the
piece before the first motor step.

To tune it, change `MAGNET_PICKUP_SETTLE_TIME` in `physical_config.py`.
The value is in seconds: `0.05` = 50 ms, `0.08` = 80 ms, and `0.10` = 100 ms.
The wait is applied in `PhysicalMoveExecutor.execute()` in
`physical_movement.py`, immediately after `magnet_on()`.
Restart the application after changing the setting so the new value is loaded.

Test pickup consistency manually on the physical board after changing the value.
