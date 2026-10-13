#!/usr/bin/env python3
"""Costola's versioned stdin/JSON-lines entry point, including a read-only probe."""

import json
import platform
import sys
from pathlib import Path


PROTOCOL_VERSION = 1


def respond(request_id, *, data=None, code=None, message=None):
    event = {
        'protocol_version': PROTOCOL_VERSION,
        'request_id': request_id,
        'type': 'result',
        'success': code is None,
    }
    if code is None:
        event['data'] = data
    else:
        event['error'] = {'code': code, 'message': message}
    print(json.dumps(event, ensure_ascii=False), flush=True)
    return 0 if code is None else 1


def main():
    # Do not import Manager: probing the executable must not initialize storage.
    try:
        request = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return respond(None, code='invalid_request', message='Expected a JSON request.')
    if not isinstance(request, dict):
        return respond(None, code='invalid_request', message='Expected a JSON object.')
    request_id = request.get('request_id')
    if not isinstance(request_id, str) or not request_id:
        return respond(None, code='invalid_request', message='A request_id is required.')
    version = request.get('protocol_version')
    if type(version) is not int or version != PROTOCOL_VERSION:
        return respond(request_id, code='unsupported_protocol', message='Expected protocol version 1.')
    # Source invocation and the frozen bundle share the same package imports.
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.engine_api import dispatch, APIError, READ_COMMANDS, MUTATIONS
    if request.get('command') != 'info':
        from core.state import StateError
        from core.storage_manager import StorageError
        from core.device import DeviceError
        from core.catalog import CatalogError
        from core.macos_copy import CopyError
        from core.preflight import PreflightError

        def progress(event):
            print(json.dumps({'protocol_version': PROTOCOL_VERSION, 'request_id': request_id,
                              'type': 'progress', **event}), flush=True)
        try:
            return respond(request_id, data=dispatch(request, emit=progress))
        except APIError as error:
            return respond(request_id, code=error.code, message=str(error))
        except (StateError, StorageError, DeviceError, CatalogError, CopyError, PreflightError, OSError) as error:
            return respond(request_id, code='blocked', message=str(error))
        except Exception:
            return respond(request_id, code='internal_error', message='The operation stopped unexpectedly. Inspect its recovery status before retrying.')
    return respond(request_id, data={
        'product': 'Costola',
        'capabilities': ['info', *READ_COMMANDS, *MUTATIONS],
        'python_version': platform.python_version(),
        'architecture': platform.machine(),
        'frozen': bool(getattr(sys, 'frozen', False)),
    })


if __name__ == '__main__':
    raise SystemExit(main())
