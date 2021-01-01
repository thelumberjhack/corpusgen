#!/usr/bin/env python3
# This code greatly inspires itself from http://aosabook.org/en/500L/a-web-crawler-with-asyncio-coroutines.html
import cgi
from collections import namedtuple
import os
import re
import logging
import urllib
import asyncio
import aiohttp
from asyncio import Queue
import time


LOGGER = logging.getLogger(__name__)

FetchStatistic = namedtuple(
    'FetchStatistic', [
        'url',
        'next_url',
        'status',
        'exception',
        'size',
        'content_type',
        'encoding',
        'num_urls',
        'num_new_urls'
    ]
)


class Crawler(object):
    """ Crawls a set of urls.
    """
    def __init__(self, roots, exclude=None, strict=True, max_redirect=10, max_tries=3, max_tasks=10, *, loop=None,
                 max_size=1024**2, file_type=None):
        self.loop = loop or asyncio.get_event_loop()
        self.roots = roots
        self.exclude = exclude
        self.strict = strict
        self.max_redirect = max_redirect
        self.max_tries = max_tries
        self.max_tasks = max_tasks
        self.queue = Queue(loop=self.loop)
        self.seen_urls = set()
        self.done = []
        self.session = aiohttp.ClientSession(loop=self.loop)
        self.root_domains = set()
        self.max_file_size = max_size
        if file_type.startswith("."):
            self.file_type = file_type
        else:
            self.file_type = "." + file_type

        for root in roots:
            parts = urllib.parse.urlparse(root)
            host, port = urllib.parse.splitport(parts.netloc)

            if not host:
                continue

            if re.match(r'\A[\d\.]*\Z', host):
                self.root_domains.add(host)

            else:
                host = host.lower()
                if self.strict:
                    self.root_domains.add(host)
                else:
                    self.root_domains.add(self.lenient_host(host))

        for root in roots:
            self.add_url(root)

        self.t0 = time.time()
        self.t1 = None

    @staticmethod
    def lenient_host(host):
        parts = host.split('.')[-2:]
        return ''.join(parts)

    @staticmethod
    def is_redirect(response):
        return response.status in (300, 301, 302, 303, 307)

    def close(self):
        """ Close resources
        :return: None
        """
        self.session.close()

    def host_ok(self, host):
        """ Can this host be crawled?
        :param host:
        :return:
        """
        host = host.lower()

        if host in self.root_domains:
            return True

        if re.match(r'\A[\d\.]*\Z', host):
            return False

        if self.strict:
            return self.host_ok_strict(host)

        else:
            return self.host_ok_lenient(host)

    def host_ok_strict(self, host):
        if host.startswith("www."):
            host = host[4:]

        else:
            host = "www." + host

        return host in self.root_domains

    def host_ok_lenient(self, host):
        return self.lenient_host(host) in self.root_domains

    def record_statistic(self, fetch_statistic):
        self.done.append(fetch_statistic)

    @asyncio.coroutine
    def parse_links(self, response):
        """ Return a FetchStatistic and list of links.
        :param response:
        :return: FetchStatistic and links.
        """
        links = set()
        content_type = None
        encoding = None
        body = yield from response.read()

        if response.status == 200:
            content_type = response.headers.get("content-type")
            pdict = {}

            if content_type:
                content_type, pdict = cgi.parse_header(content_type)

            encoding = pdict.get("charset", "utf-8")

            if content_type in ("text/html", "application/xml"):
                text = yield from response.text()

                # get all urls links
                urls = set(re.findall(r'''(?i)href=["']([^\s"'<>]+)''', text))

                if urls:
                    LOGGER.info("got {} distinct urls from {}".format(len(urls), response.url))

                for url in urls:
                    normalized = urllib.parse.urljoin(response.url, url)
                    defragmented, frag = urllib.parse.urldefrag(normalized)

                    if self.url_allowed(defragmented):
                        links.add(defragmented)

        stat = FetchStatistic(
            url=response.url,
            next_url=None,
            status=response.status,
            exception=None,
            size=len(body),
            content_type=content_type,
            encoding=encoding,
            num_urls=len(links),
            num_new_urls=len(links - self.seen_urls)
        )

        return stat, links

    @asyncio.coroutine
    def fetch(self, url, max_redirect):
        """ Fetch one url.
        :param url:
        :param max_redirect:
        :return:
        """
        tries = 0
        exception = None

        while tries < self.max_tries:
            try:
                response = yield from self.session.get(url, allow_redirects=False)

                if tries > 1:
                    LOGGER.info("try {} for {} success".format(tries, url))

                break

            except aiohttp.ClientError as client_error:
                LOGGER.info("try {} for {} raised {}".format(tries, url, client_error))
                exception = client_error

            tries += 1

        else:
            # we never broke out of the loop: all tries failed
            LOGGER.error("{} failed after {} tries".format(url, self.max_tries))
            self.record_statistic(
                FetchStatistic(
                    url=url,
                    next_url=None,
                    status=None,
                    exception=exception,
                    size=0,
                    content_type=None,
                    encoding=None,
                    num_urls=0,
                    num_new_urls=0
                )
            )

            return

        try:
            if self.is_redirect(response):
                location = response.headers['location']
                next_url = urllib.parse.urljoin(url, location)
                self.record_statistic(
                    FetchStatistic(
                        url=url,
                        next_url=next_url,
                        status=response.status,
                        exception=None,
                        size=0,
                        content_type=None,
                        encoding=None,
                        num_urls=0,
                        num_new_urls=0
                    )
                )

                if next_url in self.seen_urls:
                    return
                if max_redirect > 0:
                    LOGGER.info("redirect to {} from {}".format(next_url, url))
                    self.add_url(next_url, max_redirect - 1)
                else:
                    LOGGER.error("redirect limit reached for {} from {}".format(next_url, url))
            else:
                stat, links = yield from self.parse_links(response)
                self.record_statistic(stat)
                for link in links.difference(self.seen_urls):
                    self.queue.put_nowait((link, self.max_redirect))
                self.seen_urls.update(links)
        finally:
            yield from response.release()

    @asyncio.coroutine
    def work(self):
        """ Process Queue items forever.
        :return: None
        """
        try:
            while True:
                url, max_redirect = yield from self.queue.get()
                assert url in self.seen_urls
                yield from self.fetch(url, max_redirect)
                self.queue.task_done()
        except asyncio.CancelledError as cancelled:
            pass

    def url_allowed(self, url):
        """ Is url http or https format. Also checks the pointed url file type and size.

        :param url: given url
        :return: True if all conditions are met. False otherwise.
        """
        if self.exclude and re.search(self.exclude, url):
            return False

        parts = urllib.parse.urlparse(url)
        if parts.scheme not in ("http", "https"):
            LOGGER.debug("skipping non-http scheme in {}".format(url))
            return False
        host, port = urllib.parse.splitport(parts.netloc)
        if not self.host_ok(host):
            LOGGER.debug("skipping non-root host in {}".format(url))
            return False

        # check file type
        if not self.file_ok(url):
            LOGGER.debug("skipping non {} files".format(self.file_type))
            return False

        return True

    def add_url(self, url, max_redirect=None):
        """ Adds url to the queue if not seen before.

        :param url:
        :param max_redirect:
        :return: None
        """
        if max_redirect is None:
            max_redirect = self.max_redirect

        LOGGER.debug("adding {} {}".format(url, max_redirect))
        self.seen_urls.add(url)
        self.queue.put_nowait((url, max_redirect))

    @asyncio.coroutine
    def crawl(self):
        """ Run the crawler until all finished.
        :return: None
        """
        workers = [asyncio.Task(self.work(), loop=self.loop) for _ in range(self.max_tasks)]
        self.t0 = time.time()
        yield from self.queue.join()
        self.t1 = time.time()
        for w in workers:
            w.cancel()

    def file_ok(self, url):
        """ Is the url pointing to the correct file type? Is its size OK?
        :param url:
        :return: True if file is from a type the user requested. False otherwise.
        """
        href_path = urllib.parse.urlparse(url).path
        extension = os.path.splitext(href_path)[1]
        return extension == self.file_type

    def size_ok(self, response):
        """ Check if file size <= MAX_SIZE before downloading.
        :param response:
        :return:
        """
        raise NotImplementedError
