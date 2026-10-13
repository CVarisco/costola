#!/usr/bin/env python3
"""Read-only bundle probe for Costola; storage commands are not connected yet."""

import json
import platform
import sys


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
    if request.get('command') != 'info':
        return respond(request_id, code='unsupported_command', message='This build supports only info.')
    return respond(request_id, data={
        'product': 'Costola',
        'capabilities': ['info'],
        'python_version': platform.python_version(),
        'architecture': platform.machine(),
        'frozen': bool(getattr(sys, 'frozen', False)),
    })


if __name__ == '__main__':
    raise SystemExit(main())
