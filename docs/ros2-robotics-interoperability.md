# ROS 2 robotics interoperability

StageMesh may integrate with robotics systems through a ROS 2 adapter for
telemetry, planning, simulation, and explicitly authorized commands. ROS 2's
managed-node model provides a useful lifecycle boundary: nodes are configured,
inactive, active, or finalized under supervisory control.

References: [ROS 2 managed-node design](https://design.ros2.org/articles/node_lifecycle.html),
[ROS 2 documentation](https://docs.ros.org/).

## Lifecycle and authority

Map ROS 2 lifecycle states into StageMesh capabilities:

- **Unconfigured:** no device or command resources acquired.
- **Inactive:** configuration and diagnostics allowed; motion or physical
  actuation disabled.
- **Active:** telemetry and approved command processing enabled after health,
  authorization, and interlock checks.
- **Finalized/error:** outputs fenced; state retained for diagnosis and explicit
  recovery.

Do not let a reconnect, process restart, or automatic lifecycle transition arm a
robot. Activation requires fresh identity, capability, safety, and operator
authorization checks.

## Message and QoS contracts

Every adapter should declare message type and version, coordinate frame, units,
timestamp source, deadline, reliability, durability, queue depth, and whether
stale data may be used. Telemetry can be lossy when freshness matters; safety
or authorization state should use a policy appropriate to reliable delivery and
must expose age and sequence information.

Commands should carry a show/session identifier, command identifier, target
identity, expiry, requested time, and authorization context. Reject expired,
duplicate, out-of-order, wrong-frame, or wrong-generation commands.

## Time, frames, and recovery

Keep ROS time, system monotonic time, and StageMesh show time distinguishable.
Record clock offsets and synchronization health. Every pose or trajectory must
name its coordinate frame and transform generation; an unknown or stale frame
invalidates the command.

On node loss, DDS transport loss, stale telemetry, clock failure, or transform
failure, fence the affected command route and continue diagnostics where safe.
Recovery should reconfigure, verify state, reconcile generations, and require
explicit re-arm.

## Qualification scenarios

1. Run a simulated node through configure, activate, deactivate, error, and
   recovery transitions while confirming no physical output is armed.
2. Exercise reliable and best-effort telemetry with stale, duplicated, delayed,
   and out-of-order messages.
3. Reject commands with wrong frame, expired time, stale generation, duplicate
   identifier, or mismatched target identity.
4. Drop the node or transport during a planned action and verify route fencing
   and explicit recovery.
5. Compare recorded show time, ROS time, and monotonic timestamps against known
   synchronization tolerances.

## Integration boundary

The first adapter should support simulation and read-only telemetry before any
actuator command path. Robotics middleware availability is a host capability,
not a release assumption; StageMesh must remain testable without ROS 2 or robot
hardware installed.
