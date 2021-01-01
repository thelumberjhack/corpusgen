# Corpus #

### Description ###
Corpus is an asynchronous web crawler for you to grab a set of sample files. Then use afl-cmin to create a minset of them for later use with [AFL](http://lcamtuf.coredump.cx/afl/)

### Setup ###
Corpus has been implemented using [asyncio](https://docs.python.org/3/library/asyncio.html) module from python 3.5 therefore you need to use python >= 3.5.0.

#### Pre-requisites ####
```
virtualenvwrapper>=4.7
$ pip install mkvirtualenv
```
Virtualenv configuration is left to the discretion of the user. Once you're setup go to the next steps.

#### Installation ####
Clone source and then create virtualenv to use Corpus app as follows:
```bash
$ cd corpus
$ mkvirtualenv -p python3 -r requirements.txt corpus
```
Now you are ready to use it.

### Usage ###
```bash
$ workon corpus
(corpus) $ ./corpus.py
usage: corpus.py --roots [ROOT_DOMAINS [ROOT_DOMAINS ...]] --file_type
                 FILE_TYPE -o OUT_DIR [-i] [--select] [-r MAX_REDIRECT]
                 [-t MAX_TRIES] [-c MAX_TASKS] [-e REGEX] [-s] [-v] [-q]
                 [-m MAX_SIZE]
corpus.py: error: the following arguments are required: --roots, --file_type, -o/--output
(corpus) $
(corpus) $ ./corpus.py www.adobe.com --file-type pdf -o test
```