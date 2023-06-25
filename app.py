import time
import os.path
import asyncio
import logging
import argparse
from collections import deque
from urllib.parse import urlparse, parse_qs

import websockets
from ansi2html import Ansi2HTMLConverter


NUM_LINES = 1000
HEARTBEAT_INTERVAL = 15 #seconds

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

allowed_directories = ["./long-bottom"]
ansi_to_html_converter = Ansi2HTMLConverter(inline=True)

async def send_log_data(websocket, path):
    """
    Handles client connection, validates file access & sends log data to the client.

    Args:
        websocket: A websocket connection object.
        path: The path of the request log file.
    """
    
    logging.info('Client connected, address={}, path={}'.format(websocket.remote_address, path))

    try:
        parse_result = validate_and_parse_url(path)
        file_path = get_absolute_file_path(parse_result)

        if not is_file_accessible(file_path):
            raise ValueError('Forbidden or not found')
        
        query = parse_qs(parse_result.query)
        tail = query and query['tail'] and query['tail'][0] == '1'

        await send_file_content(websocket, file_path, tail)

    except ValueError as e:
        await handle_error(websocket, path, e)

    except Exception as e:
        handle_generic_error(websocket, path, e)

    else:
        log_client_disconnection(websocket, path)


def validate_and_parse_url(path):
    """
    Validates and parse the URL path.

    Args:
        path: A string representing the URL path.

    Returns:
        A namedtuple representing parsed URL.

    Raises.
        ValueError: If the URL cannot be parsed.
    """
    
    try:
        parse_result = urlparse(path)
        return parse_result
    
    except Exception:
        raise ValueError('Fail to parse URL')


def get_absolute_file_path(parse_result):
    """
    Get the absolute file path from the parse result.

    Args:
        parse_result: A namedtuple representing the parsed URL.

    Returns:
        A string representing the absolute file path.

    Raised:
        ValueError: If the file path is forbidden or if the file does not exist.
    """
    
    file_path = os.path.abspath("." + parse_result.path)

    if not is_file_path_allowed(file_path):
        raise ValueError('Forbidden')
    
    if not os.path.isfile(file_path):
        raise ValueError('Not Found')
    
    return file_path


def is_file_path_allowed(file_path):
    """
    Check if the file path is allowed.

    Args:
        file_path: A string representing the file path.

    Returns:
        A boolean indicating if the file path is allowed. 
    """
    
    return any(file_path.startswith(prefix) for prefix in allowed_directories)


def is_file_accessible(file_path):
    """
    Check if the file is accessible.

    Args:
        file_path: A string representing the file path.

    Returns:
        A boolean indicating whether the files is accesible.
    """
    
    return os.path.isfile(file_path) and is_file_path_allowed(file_path)


async def send_file_content(websocket, file_path, tail):
    """
    Send the file content to the client.

    Args:
        websocket: A websocket connection object.
        file_path: The path of the log file.
        tail: A boolean indicating whether to tail the file.
    """

    with open(file_path) as f:
        content = get_last_lines(f)
        await send_content(websocket, content)

        if tail:
            await tail_file(websocket, f)


def get_last_lines(file):
    """
    Get the last lines of a file.

    Args:
        file (file-like object): File to read lines from.

    Returns:
        str: HTML converted string of last lines from the file.
    """

    lines = deque(file, NUM_LINES)
    content = ' '.join(lines)

    return ansi_to_html_converter.convert(content, full=False)


async def send_content(websocket, content):
    """
    Send content to the client.

    Args:
        websocket (websockets.WebSocketServerProtocol): The websocket connection.
        content (str): The content to send.
    """

    await websocket.send(content)


async def tail_file(websocket, file):
    """
    Tail the file and send new content to the client.

    Args:
        websocket (websockets.WebSocketServerProtocol): The websocket connection.
        file (file-like object): File to read lines from.
    """

    last_heartbeat = time.time()

    while True:
        content = file.read()

        if content:
            content = ansi_to_html_converter(content, full=False)
            await send_content(websocket, content)
        else:
            await asyncio.sleep(1)

        if time.time() - last_heartbeat > HEARTBEAT_INTERVAL:
            await send_heartbeat(websocket)
            last_heartbeat = time.time()


async def send_heartbeat(websocket):
    """
    Send a heartbeat to the client and check the response.

    Args:
        websocket (websockets.WebSocketServerProtocol): The websocket connection.

    Raises:
        Exception: If pong response is not received or incorrect.
    """

    try:
        await websocket.send('ping')
        pong = await asyncio.wait_for(websocket.recv(), 5)

        if pong != 'pong':
            raise Exception()
        
    except Exception:
        raise Exception('Ping Error')


async def handle_error(websocket, path, exception):
    """
    Handle a specific error and log the client disconnection.

    Args:
        websocket (websockets.WebSocketServerProtocol): The websocket connection.
        path (str): The requested URL path.
        exception (Exception): The specific exception that occurred.
    """

    try:
        await websocket.send('<font color="red"><strong>{}</strong></font>'.format(exception))
        await websocket.close()
    except Exception:
        pass

    log_client_disconnection(websocket, path, exception)


def handle_generic_error(websocket, path, exception):
    """
    Log the client disconnection for generic exceptions.

    Args:
        websocket (websockets.WebSocketServerProtocol): The websocket connection.
        path (str): The requested URL path.
        exception (Exception): The specific exception that occurred.
    """

    log_client_disconnection(websocket, path, exception)


def log_client_disconnection(websocket, path, exception=None):
    """
    Log the disconnection of a client.

    Args:
        websocket (websockets.WebSocketServerProtocol): The websocket connection.
        path (str): The requested URL path.
        exception (Optional[Exception]): The exception that caused disconnection, if any.
    """

    message = 'Client disconnected, address={}, path={}'.format(websocket.remote_address, path)

    if exception is not None:
        message += ', exception={}'.format(exception)
    
    logging.info(message)


async def start_server(host: str, port: int):
    """
    Start the websocket server.

    Args:
        host (str): The host address to bind the server to.
        port (int): The port number to bind the server to.
    """

    async with websockets.serve(send_log_data, host, port):
        await asyncio.Future()  # Keep the server running indefinitely.


def main():
    """
    The main function that parses command-line arguments and starts the websocket server.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')  # Default host is localhost
    parser.add_argument('--port', type=int, default=8765)  # Default port is 8765
    parser.add_argument('--prefix', required=True, action='append', help='Allowed directories')
    args = parser.parse_args()

    # Add allowed directories from arguments to the global variable
    allowed_directories.extend(args.prefix)

    # Start the server with asyncio
    asyncio.run(start_server(args.host, args.port))


if __name__ == "__main__":
    main()
