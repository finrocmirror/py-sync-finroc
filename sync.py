import os
import json
import logging
import re
import pip
import site
import shutil
import subprocess
from urlparse import urlsplit, urlunsplit

from github import Github
from github.GithubException import GithubException
import hgapi

PRE_HANDLERS = logging.root.handlers


def resetLoggers():
    global PRE_HANDLERS
    logging.root.handlers = []
    logging.basicConfig(level=logging.DEBUG)
    for h in PRE_HANDLERS:
        logging.getLogger().addHandler(h)


def hg_checkout(log, repo, hg_path):
    log.info('checking out hg %s', repo)
    url = 'https://anonymous:s%40dot.com@finroc.org/hg/' + repo
    try:
        repo = hgapi.Repo(hg_path)
        repo.hg_command('pull', '--insecure', url)
    except hgapi.HgException as e:
        shutil.rmtree(hg_path, ignore_errors=True)
        hgapi.Repo.command('.', os.environ, 'clone', '--insecure', url, hg_path)


def convert_git(log, repo, hg_path, git_path):
    log.info('Converting to git %s', repo)
    if not os.path.isdir(git_path):
        shutil.rmtree(git_path, ignore_errors=True)
        os.makedirs(git_path)
    os.chdir(git_path)
    try:
        l = subprocess.check_output(["git", "rev-parse", "--verify", "--quiet"])
        if l == None or len(l) == 0:
            shutil.rmtree(git_path, ignore_errors=True)
            os.makedirs(git_path)
            raise subprocess.CalledProcessError('Nope')
    except subprocess.CalledProcessError:
        l = subprocess.check_output(['git', 'init'])
        subprocess.check_output(['git', 'config', 'core.ignoreCase', 'false'])
    fp = os.path.dirname(__file__)
    script = os.path.join(fp, 'fast_export/hg-fast-export.sh')
    try:
        subprocess.check_output([script, '-r', hg_path, ])
    except subprocess.CalledProcessError as e:
        log.exception(e)
    subprocess.check_output(['git', 'checkout'])


def send_to_github(log, repo, git_path):
    log.info('Pushing to github %s', repo)
    token = os.getenv('GITHUB_TOKEN')
    g = Github(token)
    user = g.get_user()
    try:
        repo = user.get_repo(repo)
    except GithubException as e:
        if e.status != 404:
            raise
        repo = user.create_repo(repo, private=False)
    repla = list(urlsplit(repo.clone_url))
    repla[1] = token + ':x-oauth-basic@' + repla[1]
    url = urlunsplit(repla)
    os.chdir(git_path)
    gitremotes = subprocess.check_output(['git', 'remote', '-v'])
    remotes = [re.split('[\t \(\)]', x) for x in gitremotes.split('\n')]
    origin = [x[1] for x in remotes if len(x) > 3 and x[0] == 'origin']
    if not url in origin:
        subprocess.call(['git', 'remote', 'remove', 'origin'])
        subprocess.check_output(['git', 'remote', 'add', 'origin', url])
    subprocess.check_output(['git', 'push', '--all', '-u'])


def sync_repo(log, repo):
    root = os.getenv('SYNC_ROOT','/tmp')
    hg_path = root + '/hg_clone/' + repo
    git_path = root + '/git_clone/' + repo
    hg_checkout(log, repo, hg_path)
    convert_git(log, repo, hg_path, git_path)
    send_to_github(log, repo, git_path)


def script_main(log):
    import requests
    import html5lib

    page = 'http://www.finroc.org/browser'
    doc = html5lib.parse(requests.get(page).content,namespaceHTMLElements=False)
    table = doc.find('body')
    alltags = [(a.get('href'), a) for a in table.findall('.//a[@class="dir"]')]
    repos = [x[0].split('/browser/')[1] for x in alltags]
    log.info('\n'.join(repos))
    for repo in repos:
        sync_repo(log, repo)


def lambda_handler(event, context):
    resetLoggers()
    log = logging.getLogger(__name__)
    log.debug('Received event: ' + json.dumps(event, indent=2))
    pip.main(['install', 'requests', 'html5lib', 'mercurial', 'hgapi', '-t', '/tmp/stage'])
    resetLoggers()
    site.addsitedir('/tmp/stage')
    log = logging.getLogger(__name__)
    try:
        script_main(log)
    except ImportError:
        log.exception('Import failed')
    return 'OK'


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
    if False:
        sync_repo(log, 'admin_finroc_debian')
    elif False:
        sync_repo(log, 'rrlib_crash_handler')
        sync_repo(log, 'admin_finroc_debian')
    else:
        script_main(log)
