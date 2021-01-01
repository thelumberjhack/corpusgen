#!/usr/bin/env python
import argparse
import asyncio
import logging
import sys

from crawler.crawler import *


class Corpus(object):

    @staticmethod
    def parse_args():
        parser = argparse.ArgumentParser(
            add_help=False,
            description="Asynchronous web crawler for initial fuzz corpus",
            epilog="Exit status is 0 for non-failures, -1 otherwise.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            prog="corpus.py"
        )

        # Mandatory arguments
        mand = parser.add_argument_group("Mandatory arguments")
        mand.add_argument("--roots", nargs="*", required=True, dest="root_domains",
                          help="Root domains to start crawling from")
        mand.add_argument("--file-type", type=str, required=True, dest="file_type",
                          help="File type you wanna download")
        mand.add_argument("-o", "--output", type=str, required=True, dest="out_dir",
                          help="Output directory to store the files.")

        # Optional arguments
        opt = parser.add_argument_group("Optional arguments")
        opt.add_argument("-i", "--iocp", action="store_true", default=False, dest="iocp",
                         help="Use IOCP event loop (Windows only)")
        opt.add_argument("--select", action="store_true", default=False, dest="select",
                         help="Use Select event loop instead of default")
        opt.add_argument("-r", "--max-redirect", type=int, default=10, dest="max_redirect",
                         help="Limit redirection chains (for 301, 302, etc.)")
        opt.add_argument("-t", "--max_tries", type=int, default=3, dest="max_tries",
                         help="Limit retries on network errors")
        opt.add_argument("-c", "--max-tasks", type=int, default=100, dest="max_tasks",
                         help="Limit concurrent connections")
        opt.add_argument("-e", "--exclude", type=str, metavar="REGEX", default=None, dest="exclude",
                         help="Exclude matching URLs")
        opt.add_argument("-s", "--strict", action="store_true", default=True,
                         help="Strict host matching (default)")
        opt.add_argument("-l", "--lenient", action="store_false", default=False,
                         dest="strict", help="Lenient host matching")
        opt.add_argument("-v", "--verbose", action="count", dest="log_level", default=2,
                         help="Verbose logging (repeat for more details)")
        opt.add_argument("-q", "--quiet", action="store_const", const=0, default=2, dest="log_level",
                         help="Only log errors")
        opt.add_argument("-m", "--max-size", type=str, default="1M", dest="max_size",
                         help="Maximum file size")

        return parser.parse_args()

    @staticmethod
    def fix_url(url):
        """Prefix a schema-less URL with http://."""
        if '://' not in url:
            url = 'http://' + url
        return url

    @classmethod
    def main(cls):
        args = cls.parse_args()

        # Logging levels
        levels = [logging.ERROR, logging.WARN, logging.INFO, logging.DEBUG]
        logging.basicConfig(level=levels[min(args.log_level, len(levels) - 1)])

        if args.iocp:
            # TODO: add check if we actually are running on windows
            from asyncio.windows_events import ProactorEventLoop
            loop = ProactorEventLoop()
            asyncio.set_event_loop(loop)

        elif args.select:
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)

        else:
            # Default behavior
            loop = asyncio.get_event_loop()

        roots = {cls.fix_url(root) for root in args.root_domains}

        crawler = Crawler(
            roots,
            exclude=args.exclude,
            strict=args.strict,
            max_redirect=args.max_redirect,
            max_tries=args.max_tries,
            max_tasks=args.max_tasks,
            file_type=args.file_type
        )

        try:
            loop.run_until_complete(crawler.crawl())
        except KeyboardInterrupt:
            sys.stderr.flush()
            logging.error("Interrupted by user")
            return -1
        finally:
            crawler.close()

            # required for actual aiohttp resource cleanup
            loop.stop()
            loop.run_forever()

            loop.close()

            return 0


if __name__ == '__main__':
    sys.exit(Corpus.main())
