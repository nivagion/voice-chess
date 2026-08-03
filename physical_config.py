"""Hardware calibration shared by the application and calibration utility.

This module is deliberately data-only. Importing it never touches GPIO.
Pin numbers use BCM numbering and are preserved from the original calibration
script.
"""

SQUARE_SIZE_CM = 7.0
HORIZONTAL_STEPS_PER_SQUARE = 352
VERTICAL_STEPS_PER_SQUARE = 355

STEP_HIGH_TIME = 0.0017
STEP_LOW_TIME = 0.0002
MOVE_SETTLE_TIME = 0.10

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
