# Lights Board

## Role

The lights board owns the actual light outputs.

It is responsible for:

- applying headlight, tail light, brake light, and turn signal states
- mapping requested light bits to GPIO outputs
- preserving safe defaults when comms are lost

## What it does

Typical lights-board behavior includes:

- enabling or disabling outputs based on requested state
- keeping brake and turn behavior consistent
- timing out requested state when messages stop arriving
- turning outputs off when it no longer trusts the source state

## Communication responsibilities

In the target architecture:

- the motor board sends light requests to the lights board
- the lights board confirms receipt of the request
- the lights board should be able to fail safe if comms stop arriving

## Important notes

- The lights board should not be a passive sink.
- It should confirm that it received the request.
- If the display stops driving light updates through the motor board, the lights board should fall back to safe outputs.

## Code areas

Relevant code is usually in:

- `03_diy_lights_board/main.py`
- `common/espnow_protocol.py`
- `common/lights_bits.py`
