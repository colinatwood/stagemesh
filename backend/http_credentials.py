"""Private, bounded credential snapshots for the HTTP control bridge."""
import json
import os
import stat


TOKEN_KEYS = frozenset({
    'STAGEMESH_API_TOKEN', 'STAGEMESH_MONITOR_API_TOKEN',
    'STAGEMESH_ADMIN_API_TOKEN', 'STAGEMESH_AUTH_PROXY_TOKEN',
    'STAGEMESH_ADAPTER_REPORT_TOKEN',
})


def credential_environment(environ=None):
    env = dict(os.environ if environ is None else environ)
    path = env.get('STAGEMESH_HTTP_CREDENTIAL_FILE', '')
    if not path:
        return env
    try:
        if not os.path.isabs(path):
            raise ValueError('absolute path required')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o077 or before.st_size > 16384):
                raise ValueError('invalid file')
            data = stream.read(16385)
            after = os.fstat(stream.fileno())
            if (len(data) > 16384 or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                raise ValueError('changed file')
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate key')
                result[key] = value
            return result
        tokens = json.loads(data.decode('utf-8'), object_pairs_hook=unique_pairs)
        if not isinstance(tokens, dict) or not set(tokens) <= TOKEN_KEYS:
            raise ValueError('invalid keys')
        if 'STAGEMESH_API_TOKEN' not in tokens:
            raise ValueError('missing control credential')
        for token in tokens.values():
            if (not isinstance(token, str) or not 32 <= len(token) <= 512
                    or not token.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in token)):
                raise ValueError('invalid token')
        if len(set(tokens.values())) != len(tokens):
            raise ValueError('overlapping credentials')
    except (OSError, ValueError, AttributeError, RecursionError):
        raise PermissionError('HTTP credential file unavailable or invalid') from None
    for key in TOKEN_KEYS:
        env.pop(key, None)
    env.update(tokens)
    env['STAGEMESH_REQUIRE_API_TOKEN'] = '1'
    return env
