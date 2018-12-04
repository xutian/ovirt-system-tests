#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
from __future__ import print_function
import functools
import os
import re
import subprocess
import time
from datetime import datetime
import sys

import nose.tools as nt
import ovirtsdk4.types as types
import test_utils
from lago import utils
from nose import SkipTest
from ovirtlago import testlib
from ovirtsdk.xml import params
from test_utils.constants import *
from test_utils.selenium_constants import *
from test_utils.navigation.driver import *


from selenium import webdriver
from selenium.common.exceptions import (ElementNotVisibleException,
                                        NoSuchElementException,
                                        WebDriverException)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


@testlib.with_ovirt_prefix
def get_engine_ip(prefix):
    engine = prefix.virt_env.engine_vm()
    return engine.ip()


@testlib.with_ovirt_prefix
def get_engine_admin_password(prefix):
    engine = prefix.virt_env.engine_vm()
    return engine.metadata['ovirt-engine-password']


URL = "https://%s/ovirt-engine/webadmin" % get_engine_ip()
USERNAME = 'admin'
PASSWORD = get_engine_admin_password()

SS_PATH = os.path.join(
    os.environ.get('OST_REPO_ROOT'),
    'exported-artifacts/screenshots%s/' %
    (os.environ.get('OST_DC_VERSION', ''),)
)

HUB_CONTAINER_IMAGE = 'selenium/hub:3.9.1-actinium'
FIREFOX_CONTAINER_IMAGE = 'selenium/node-firefox-debug:3.9.1-actinium'
CHROME_CONTAINER_IMAGE = 'selenium/node-chrome-debug:3.9.1-actinium'
NETWORK_NAME = 'grid'
# selenium grid actinium release uses these versions:
FIREFOX_VERSION = '58.0.1'
CHROME_VERSION = '64.0.3282.140'

HUB_CONTAINER_NAME = 'selenium-hub'
FIREFOX_CONTAINER_NAME = 'grid_node_firefox'
CHROME_CONTAINER_NAME = 'grid_node_chrome'

BROWSER_PLATFORM = 'LINUX'

GRID_STARTUP_DELAY = 20

WINDOW_WIDTH = 1680
WINDOW_HEIGHT = 1050

global ovirt_driver
global hub_url
global ss_prefix_browser_name


def log(*args):
    print(*args)


def _ss_prefix():
    global ss_prefix_browser_name
    now = datetime.now()
    browser = ''
    if ss_prefix_browser_name != None:
        browser = '_' + ss_prefix_browser_name
    return "%d%02d%02d_%02d%02d%02d_%03d%s" % (now.year, now.month, now.day, now.hour, now.minute, now.second, now.microsecond/1000, browser)


def _shell(args, message=None):
    if message:
        log(message)
    print("executing shell: " + " ".join(args))
    process = subprocess.Popen(args,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    out, err = process.communicate()
    log(out)
    log(err)


def _get_ip(hostname):
    process = subprocess.Popen(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", hostname],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    out, err = process.communicate()
    pattern = re.compile(r'\s+')
    ip = re.sub(pattern, '', out)
    return ip


def _docker_cleanup():
    _shell(["docker", "ps"])
    _shell(["docker", "rm", "-f", CHROME_CONTAINER_NAME, FIREFOX_CONTAINER_NAME, HUB_CONTAINER_NAME])
    _shell(["docker", "kill", CHROME_CONTAINER_NAME, FIREFOX_CONTAINER_NAME, HUB_CONTAINER_NAME])
    _shell(["docker", "ps"])
    _shell(["docker", "network", "ls"])
    _shell(["docker", "network", "rm", NETWORK_NAME])
    _shell(["docker", "network", "ls"])


def _get_firefox_capabilities():
    capabilities = DesiredCapabilities.FIREFOX.copy()
    capabilities['platform'] = BROWSER_PLATFORM
    capabilities['version'] = FIREFOX_VERSION
    capabilities['browserName'] = 'firefox'
    capabilities['acceptInsecureCerts'] = True
    return capabilities


def _get_chrome_capabilities():
    capabilities = DesiredCapabilities.CHROME.copy()
    capabilities['platform'] = BROWSER_PLATFORM
    capabilities['version'] = CHROME_VERSION
    return capabilities


def init():
    # make screenshot directory
    os.makedirs(SS_PATH)


def start_grid():
    global hub_url

    _docker_cleanup()

    _shell(["docker", "network", "ls"])
    _shell(["docker", "network", "create", NETWORK_NAME], "creating docker network for grid")
    _shell(["docker", "network", "ls"])

    _shell(["docker", "run", "-d", "-p", "4444:4444", "--net", NETWORK_NAME, "--name", HUB_CONTAINER_NAME, HUB_CONTAINER_IMAGE], "starting hub")
    log("getting ip of hub")
    hub_ip = _get_ip(HUB_CONTAINER_NAME)
    if hub_ip == "":
        raise RuntimeError("could not get ip address of selenium hub. See previous messages for probable docker failure")

    _shell(["docker", "run", "-d", "--net", NETWORK_NAME, "-e", "HUB_HOST=" + hub_ip, "-v", "/dev/shm:/dev/shm", "--name", CHROME_CONTAINER_NAME, CHROME_CONTAINER_IMAGE],
           "starting chrome")
    log("getting ip of chrome")
    chrome_ip = _get_ip(CHROME_CONTAINER_NAME)

    _shell(["docker", "run", "-d", "--net", NETWORK_NAME, "-e", "HUB_HOST=" + hub_ip, "-v", "/dev/shm:/dev/shm", "--name", FIREFOX_CONTAINER_NAME, FIREFOX_CONTAINER_IMAGE],
           "starting firefox")
    log("getting ip of firefox")
    firefox_ip = _get_ip(FIREFOX_CONTAINER_NAME)

    # give the grid a bit to start up
    log("waiting %s sec for grid to initialize..." % GRID_STARTUP_DELAY)
    time.sleep(GRID_STARTUP_DELAY)

    _shell(["docker", "ps"])

    # proxy is used in CI -- turn off proxy for webdriver
    # TODO is there a better way, perhaps via webdriver api?
    os.environ["http_proxy"] = ""

    # these are for debugging -- if the tests fail, it helps to know the nodes were ok
    _shell(["curl", "http://" + hub_ip + ":4444/grid/console"], "checking hub node")
    _shell(["curl", "http://" + chrome_ip + ":5555/wd/hub/static/resource/hub.html"], "checking chrome node")
    _shell(["curl", "http://" + firefox_ip + ":5555/wd/hub/static/resource/hub.html"], "checking firefox node")

    hub_url = 'http://' + hub_ip + ':4444/wd/hub'
    log("resolved hub url: %s" % hub_url)


def initialize_chrome():
    global ss_prefix_browser_name
    ss_prefix_browser_name = "chrome"
    _init_driver(_get_chrome_capabilities())


def initialize_firefox():
    global ss_prefix_browser_name
    ss_prefix_browser_name = "firefox"
    _init_driver(_get_firefox_capabilities())


def _init_driver(capabilities):
    global ovirt_driver
    global hub_url

    try:
        log("_init_browser, connecting to hub at " + hub_url)

        driver = webdriver.Remote(
            command_executor=hub_url,
            desired_capabilities=capabilities
        )

        ovirt_driver = Driver(driver)

    except WebDriverException as e:
        log(e)
        log("WebDriverException in _init_browser connecting to hub")
        raise e

    log("setting window size")
    driver.set_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)

    log("navigating to engine at %s" % URL)
    driver.get(URL)
    ovirt_driver.save_screenshot('%s%s_welcome.png' % (SS_PATH, _ss_prefix()), 5)


def login():
    """
    login to oVirt webadmin
    """
    global ovirt_driver

    ovirt_driver.save_screenshot('%s%s_login_screen.png' % (SS_PATH, _ss_prefix()), 1)
    elem = ovirt_driver.wait_for_id(SEL_ID_LOGIN_USERNAME)
    elem.send_keys(USERNAME)
    elem = ovirt_driver.wait_for_id(SEL_ID_LOGIN_PASSWORD)
    elem.send_keys(PASSWORD)
    ovirt_driver.save_screenshot('%s%s_login_screen.png' % (SS_PATH, _ss_prefix()), 1)
    elem.send_keys(Keys.RETURN)
    ovirt_driver.save_screenshot('%s%s_logged_in.png' % (SS_PATH, _ss_prefix()), 5)


def left_nav():
    """
    click around on a few main views
    """
    global ovirt_driver

    ovirt_driver.hover_to_id(SEL_ID_COMPUTE_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_hover_compute.png' % (SS_PATH, _ss_prefix()), 1)
    ovirt_driver.id_click(SEL_ID_CLUSTERS_MENU)
    time.sleep(1)
    ovirt_driver.save_screenshot('%s%s_left_nav_clicked_clusters.png' % (SS_PATH, _ss_prefix()), 1)

    ovirt_driver.hover_to_id(SEL_ID_COMPUTE_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_hover_compute.png' % (SS_PATH, _ss_prefix()), 1)
    ovirt_driver.id_click(SEL_ID_HOSTS_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_clicked_hosts.png' % (SS_PATH, _ss_prefix()), 1)

    # TODO(gs) fix storage. The IDs are missing
    # ovirt_driver.hover_to_id(SEL_ID_STORAGE_MENU)
    # ovirt_driver.save_screenshot('%s%s_left_nav_hover_storage.png' % (SS_PATH, _ss_prefix()), 1)
    # ovirt_driver.id_click(SEL_ID_DOMAINS_MENU)
    # ovirt_driver.save_screenshot('%s%s_left_nav_clicked_domains.png' % (SS_PATH, _ss_prefix()), 1)

    ovirt_driver.hover_to_id(SEL_ID_COMPUTE_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_hover_compute.png' % (SS_PATH, _ss_prefix()), 1)
    ovirt_driver.id_click(SEL_ID_TEMPLATES_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_clicked_templates.png' % (SS_PATH, _ss_prefix()), 1)

    ovirt_driver.hover_to_id(SEL_ID_COMPUTE_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_hover_compute.png' % (SS_PATH, _ss_prefix()), 1)
    ovirt_driver.id_click(SEL_ID_POOLS_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_clicked_pools.png' % (SS_PATH, _ss_prefix()), 1)

    ovirt_driver.hover_to_id(SEL_ID_COMPUTE_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_hover_compute.png' % (SS_PATH, _ss_prefix()), 1)
    ovirt_driver.id_click(SEL_ID_VMS_MENU)
    ovirt_driver.save_screenshot('%s%s_left_nav_clicked_vms.png' % (SS_PATH, _ss_prefix()), 1)


def close_driver():
    global ovirt_driver

    log("shutting down driver")
    ovirt_driver.shutdown()


def cleanup():
    close_driver()

    log("_docker_cleanup")
    _docker_cleanup()


_TEST_LIST = [
    init,
    start_grid,
    initialize_chrome,
    login,
    left_nav,
    close_driver,
    initialize_firefox,
    login,
    left_nav,
    cleanup,
]


def test_gen():
    for t in test_utils.test_gen(_TEST_LIST, test_gen):
        yield t
