# Astra checkpoint 61 validation — isolated Linux rootfs packaging qualification

Checkpoint 61 turns the existing staged-installer tests into a repeatable installed qualification helper. It still does **not** claim a clean production host or physical device-permission qualification.

## Qualification helper

`scripts/stagemesh-package-qualify.py` creates a fresh temporary rootfs and exercises the real packaging path:

1. install the built native engine, backend/frontend/schemas, helpers and packaged service files with `scripts/install-linux.sh`;
2. provision the staged `stagemesh` service account using `systemd-sysusers`;
3. provision `/var/lib/stagemesh` using `systemd-tmpfiles`;
4. verify the staged account exists and the state directory has numeric ownership matching that account with mode `0750`;
5. verify both source service units with `systemd-analyze verify`;
6. prove the installer did not create an enablement symlink;
7. create persistent state, reinstall, and prove the bytes remain unchanged;
8. execute the installed `stagemesh-qualify.py` helper;
9. uninstall normally and prove program files are removed while persistent state remains;
10. run explicit `--purge-data` and prove persistent state is removed.

The helper is installed into `/usr/libexec/stagemesh/` so packaged builds can run the same reference exercise.

## Reference result

The checkpoint run against the fresh RT build reports:

- `passed: true`;
- `qualification: isolated-rootfs-reference`;
- sysusers and tmpfiles provisioning passed;
- state directory mode `0750` with staged StageMesh UID/GID ownership;
- both systemd units verified;
- service auto-enable remained false;
- reinstall and ordinary uninstall preserved state;
- explicit purge removed state;
- `cleanHostQualified: false`;
- `hardwarePermissionsQualified: false`.

## Full gate

- Focused installer/package qualification tests pass **6/6**.
- Release Python suite passes **616 tests**.
- RT native CTest passes **2/2**; native source is unchanged from checkpoint 60.
- Automation-performance passes.
- All **126 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

`PKG-033` remains open for a real clean Linux host/VM boot/service exercise, and `PKG-034` remains open for actual audio/MIDI/device permission qualification under the service account. The project license remains an owner decision.
