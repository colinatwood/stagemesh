# LinuxCNC motion interoperability

StageMesh may integrate with machine or robotics controllers through a
simulation-first motion adapter. LinuxCNC's Hardware Abstraction Layer (HAL)
separates real-time signal processing from non-real-time configuration and
interfaces, which is a useful boundary for StageMesh as well.

References: [LinuxCNC HAL manual](https://www.linuxcnc.org/docs/devel/html/en/man/man3/hal.3.html),
[LinuxCNC HAL tutorial](https://www.linuxcnc.org/docs/stable/html/hal/tutorial.html).

## Separate planning from motion

StageMesh should produce inspectable, versioned motion intents rather than
writing directly to pins or drives. An intent should include target identity,
coordinate frame, units, limits, timing, generation, expiry, and authorization.
The controller adapter is responsible for translating that intent into the
machine's native interface and reporting acceptance, execution, and fault
state.

Keep planning, preview, controller communication, real-time control, and
physical I/O as separate layers. LinuxCNC or another controller may own the
hard real-time loop; StageMesh must not assume that a normal user-space process
can provide machine-safe timing.

## Safety and lifecycle

Require explicit states such as unconfigured, homing-required, ready,
simulating, armed, moving, faulted, and emergency-stopped. Homing, travel
limits, soft limits, feed/velocity limits, collision zones, and external
interlocks must be visible preconditions. A controller reconnect or process
restart must return to a non-armed state.

HAL-style signals should be observable and testable individually. Preserve the
distinction between commanded position, measured position, enable state, limit
state, fault state, and emergency-stop state.

## Qualification scenarios

1. Run a simulated controller with known axes and verify coordinate frames,
   units, limits, and generated motion intents.
2. Confirm that homing, missing limits, stale feedback, or mismatched generation
   prevents arming.
3. Exercise delayed, duplicated, interrupted, and out-of-order commands; verify
   bounded queues and deterministic rejection.
4. Trigger controller loss, limit activation, watchdog expiry, and emergency
   stop; confirm immediate route fencing and explicit recovery.
5. Compare planned, commanded, and measured trajectories without connecting
   physical actuators.

## Integration boundary

Start with a fake HAL/controller and recorded telemetry. Add a real controller
only after the software qualification passes and the machine's independent
guards have been reviewed. LinuxCNC availability, a real-time kernel, and
machine hardware are host qualifications, not requirements for StageMesh's
portable software release.
