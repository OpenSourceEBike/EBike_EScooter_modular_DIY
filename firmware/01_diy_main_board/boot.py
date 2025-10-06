# boot.py — enter safe mode automatically after crash/fault reset
import machine
import sys

# Reset cause constants:
# machine.PWRON_RESET      1   # Power-on
# machine.HARD_RESET       2   # machine.reset()
# machine.WDT_RESET        3   # Hardware watchdog
# machine.DEEPSLEEP_RESET  4   # Deep sleep wakeup
# machine.SOFT_RESET       5   # Ctrl-D soft reset from REPL

cause = machine.reset_cause()
print("Reset cause:", cause)

# Define what counts as "faulty" reset
FAULT_CAUSES = (machine.HARD_RESET,)

if cause in FAULT_CAUSES:
    print("Entering safe mode...")
    sys.exit()
