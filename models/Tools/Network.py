import logging


async def fetch(session, url, headers=''):
    # https://docs.aiohttp.org/en/stable/http_request_lifecycle.html#how-to-use-the-clientsession
    '''Allows retrieval of a url with a session added
        '''
    async with session.get(url, headers=headers) as response:
        logging.debug(f"HTTP Status for {url}: {response.status}")
        if 'X-RateLimit-Remaining-minute' in response.headers:
            logging.debug(
                f"Remaining Requests per minute: {response.headers['X-RateLimit-Remaining-minute']}")

        # Check the status code
        # Status codes which indicate an error
        error_codes = [400, 404, 500]
        if response.status == 200:
            # Return the response text
            return await response.text()
        elif response.status in error_codes:
            raise LookupError(
                f'HTTP statuscode {response.status}, reason: {response.reason} for {url}')
