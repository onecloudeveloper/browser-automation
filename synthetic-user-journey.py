# -*- coding: utf-8 -*-
# ****************************************************************/
# Author  : Mohamed Ismail (mohamed.ismail@tryzens.com)           /
# Company : Tryzens                                               /
# Date    : 9 Jan 2016                                            /
# Version : 3.2.3                                                 /
# Description : This script is used to simulate customer journey  /
# ****************************************************************/
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.common.exceptions import NoSuchElementException, NoAlertPresentException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, WebDriverException
import selenium.webdriver.support.expected_conditions as EC 
import browsermobproxy
import urllib, json, unittest, re
import os, sys, datetime, time, signal, traceback, getopt
import logging, inspect
import commands

# configure logging
RELATIVE_PATH         = "/tmp"
SYSTEM_LOG_FILE_PATH  = os.path.dirname(os.path.realpath(__file__))
LOG_FILE              = "userjourney.log"
CONFIG_FILE           = "journey.conf"
steps                 = dict()
EXIT_STATUS_FAILURE   = 1
EXIT_STATUS_SUCCESS   = 0
EXIT_STATUS_CODE      = EXIT_STATUS_FAILURE

# setup logging
#sys.tracebacklimit = 0
FORMAT = "%(asctime)-15s %(source)-9s %(user)-8s [%(levelname)-8s] %(message)s"
LOG_HEAD  = {'source': 'SELENIUM', 'user': 'bi-robot'}
logger = None

def configurePath():

    global logger 
    os.system('mkdir -p ' + RELATIVE_PATH + '/old') 
    os.system('mv -f ' + RELATIVE_PATH + '/*.har ' + RELATIVE_PATH + "/old 2> /dev/null") 
    os.system('mv -f ' + RELATIVE_PATH + '/*.png ' + RELATIVE_PATH + "/old 2> /dev/null") 
    os.system('mv -f ' + RELATIVE_PATH + '/' + LOG_FILE + ' ' + RELATIVE_PATH + "/old 2> /dev/null") 

    #print RELATIVE_PATH + "/" + LOG_FILE
    logging.basicConfig(
        filename = RELATIVE_PATH + '/' + LOG_FILE,
        format = FORMAT
    )
    logger = logging.getLogger('userjourney')
    logger.setLevel(logging.DEBUG)
    logger.info("initialising script", extra=LOG_HEAD)


# class structure to hold user journey step definition
class UserJourneyStep:
    seq = ""
    seq_sub = ""
    name = ""
    method = ""
    url = ""
    xpath = ""
    xpath_attr = ""
    tls = False 

    def __init__(self):
        self.seq = ""
        self.seq_sub = ""
        self.name = ""
        self.method = ""
        self.url = "" 
        self.tls = False 
        self.xpath = ""
        self.xpath_attr = ""

    def setField(self, field, value):
        setattr(self, field, value)


#this method will send the exist status code to the caller
def sendExitStatus(exitCode = 1):
    global EXIT_STATUS_CODE
    EXIT_STATUS_CODE = exitCode

    logger.info("exit status code is: %s", str(EXIT_STATUS_CODE), extra=LOG_HEAD)
    sys.exit( EXIT_STATUS_CODE )


# method to load user configuration
def loadConfigs():

    # ---------- Read gloabl configs ----------
    expr = re.compile(r"^SYSTEM_([^\=]+?)\=\"(.*?)\"")
    try:
        fhndl = open(RELATIVE_PATH + "/" + CONFIG_FILE)
    except IOError as e:
        logger.error("I/O error({0}): {1}".format(e.errno, e.strerror), extra=LOG_HEAD) 
        sendExitStatus()

    for line in fhndl: 
        if expr.match(line):
            m = re.search('(.*?)\="(.*)"', line)
            parameter = m.group(1)
            value = m.group(2)
            if value.isdigit(): 
                globals()[parameter] = int(value)
            else:
                globals()[parameter] = value

    globals()["OUTPUT_FILE_HEAD"] = SYSTEM_WEB_DOMAIN.replace("/", "_")

    logger.info("------- User parameters--------", extra=LOG_HEAD)
    logger.info("SYSTEM_WEB_DOMAIN                 : %s", SYSTEM_WEB_DOMAIN, extra=LOG_HEAD)
    logger.info("SYSTEM_WEB_DOMAIN_URL             : %s", SYSTEM_WEB_DOMAIN_URL, extra=LOG_HEAD)
    logger.info("SYSTEM_SELENIUM_HUB_URL           : %s", SYSTEM_SELENIUM_HUB_URL, extra=LOG_HEAD)
    logger.info("SYSTEM_BROWSER_PROXY              : %s", SYSTEM_BROWSER_PROXY, extra=LOG_HEAD)
    logger.info("SYSTEM_GRAYLOG_REST_URL           : %s", SYSTEM_GRAYLOG_REST_URL, extra=LOG_HEAD)
    logger.info("SYSTEM_JOURNEY_NAME               : %s", SYSTEM_JOURNEY_NAME, extra=LOG_HEAD)
    logger.info("SYSTEM_THINK_TIME_BETWEEN_STEPS   : %s seconds", str(SYSTEM_THINK_TIME_BETWEEN_STEPS), extra=LOG_HEAD)
    logger.info("SYSTEM_SLEEP_TIME_BEFORE_TERMINATE: %s seconds", str(SYSTEM_SLEEP_TIME_BEFORE_TERMINATE), extra=LOG_HEAD)
    logger.info("SYSTEM_SLA_REQUEST_TIME_THRESHOLD : %s seconds", str(SYSTEM_SLA_REQUEST_TIME_THRESHOLD),  extra=LOG_HEAD)
    logger.info("SYSTEM_SLA_PAGE_TIME_THRESHOLD    : %s seconds", str(SYSTEM_SLA_PAGE_TIME_THRESHOLD), extra=LOG_HEAD)
    logger.info("SYSTEM_LOG_FILE_PATH              : %s", SYSTEM_LOG_FILE_PATH, extra=LOG_HEAD)
    logger.info("---- now into real business ----", extra=LOG_HEAD)
    
    # ---------- Read the step definitions ----------
    fhndl.seek(0)
    expr = re.compile(r"^\[[^\[]+?\]")

    for line in fhndl: 
        if expr.match(line):
            t = line.replace("[","").replace("]","").replace("step_","").rstrip()
            steps[t] =  UserJourneyStep()

    # Read attributes of each step 
    fhndl.seek(0)
    for line in fhndl: 
        for i in (steps.keys()):    
            m = re.search('(?<=step_'+ i +')_(.*?)="(.*)"', line)
            if m != None:
                field = m.group(1)
                tmp_value = (m.group(2)).replace('\\','')
                if field == "tls":
                   value = False
                   if tmp_value == "on":
                      value = True
                   getattr(steps[i], 'setField')(field, value)
                else:
		   getattr(steps[i], 'setField')(field, tmp_value)
                continue

    fhndl.close()


def getFrame():
    frame = inspect.stack()[1][0]
    info = inspect.getframeinfo(frame)
    return "lineno: " + str(info.lineno)


# class to handle timeout
class timeout:
    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message
    def handle_timeout(self, signum, frame):
        raise TimeoutException
    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)
    def __exit__(self, type, value, traceback):
        signal.alarm(0)
 
 
class SyntheticUserJourney(unittest.TestCase):

    def getTimestamp(self):
        return datetime.datetime.fromtimestamp(time.time()).strftime('%d-%m-%Y %H:%M:%S')


    def getSessionId(self):
        
        global exception, Error_Message, sessionId
        cookie_found = False
        cookies = None
        try:
            with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                cookies = driver.get_cookies()
        except TimeoutException, err:
            pass

        if cookies != None:
            logger.debug(">>>>> looking to extract the session id", extra=LOG_HEAD)
            for session_key in PLATFORM_SESSION_IDENTIFIER:     
                for cookie in cookies:
                    if cookie['name'] == session_key:
                        sessionId = str(cookie['value'])
                        cookie_found = True
                        break
            
                if cookie_found == True: 
                    break

        logger.debug(">>>>> after exiting the loop in getSessionId()", extra=LOG_HEAD)
        return sessionId
  

    def setUp(self):
        global driver, proxi, final_exception, exception, Error_Message

        try:
            loadConfigs()

            logger.debug(">>>>> initialising browsermobproxy....", extra=LOG_HEAD)
            init_element = "browsermobproxy"
            with timeout( seconds=WEBDRIVER_PROXY_TIMEOUT ):
               proxi = browsermobproxy.Client(SYSTEM_BROWSER_PROXY)
               proxi.blacklist('.*zopim.*', 200)

            logger.debug(">>>>> initialising webdriver....", extra=LOG_HEAD)
            init_element = "webdriver"
            with timeout( seconds=WEBDRIVER_PROXY_TIMEOUT ):
               driver = webdriver.Remote(
                   command_executor=SYSTEM_SELENIUM_HUB_URL,
                   desired_capabilities=capabilities,
                   proxy=proxi
               )
        
            driver.maximize_window()
            #driver.implicitly_wait(SYSTEM_SLA_PAGE_TIME_THRESHOLD)
            driver.set_page_load_timeout(SYSTEM_SLA_REQUEST_TIME_THRESHOLD)

        except TimeoutException, err:
            logger.error("****** Timeout occured while initialising %s ******", init_element, extra=LOG_HEAD)
            logger.info("Exit status code is: %s", str(EXIT_STATUS_CODE), extra=LOG_HEAD)
            sys.exit(1)

        except Exception as err:
            exception = "WebDriverException"
            Error_Message = "Unknown webdriver error occurred"
            final_exception = exception
            err_msg = err
            if len(err) >= 60:
                err_msg = err[:60]
            logger.error("exception: %s [%s]", err_msg, getFrame(), extra=LOG_HEAD)
            self.tearDown()           

        self.base_url = "http://" + SYSTEM_WEB_DOMAIN
        self.base_url_tls = "https://" + SYSTEM_WEB_DOMAIN
        self.verificationErrors = []
        self.accept_next_alert = True


    def execute_step(self, action, stepSeq, stepSeqSub, stepName, uri, xpath="", addAttr="", tls=False):

        global sessionId, currRequest, numRequests, total_byteSize, exception, stepStarted, startTime, final_exception, journey_status, Error_Message
        exception = None

        logger.info("BEGIN step %s.%s - %s", stepSeq, stepSeqSub, stepName, extra=LOG_HEAD) 

        if stepStarted == False:
            stepStarted = True
            proxi.new_har()
            startTime = time.time() * 1000
            endTime = startTime 

        base_url = self.base_url 

        try:
            logger.debug(">>>>> ENTER executing step {0}.{1} action {2}".format(str(stepSeq), str(stepSeqSub), action), extra=LOG_HEAD)
            if action == "get":
                if tls == True:
                    base_url = self.base_url_tls 
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    driver.get(base_url + uri)

            elif action == "hover":
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    hndl = driver.find_element_by_xpath(xpath)
                    ActionChains(driver).move_to_element(hndl).perform() 

            elif action == "click":
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    driver.find_element_by_xpath(xpath).click()

            elif action == "lookup" and addAttr != "":
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    lookupObj = driver.find_element_by_xpath(xpath).get_attribute(addAttr)
                    logger.info("lookup %s found in response : %s", addAttr, lookupObj, extra=LOG_HEAD)

            elif action == "clear":
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    driver.find_element_by_xpath(xpath).clear()

            elif action == "keyin" and addAttr != "":
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    driver.find_element_by_xpath(xpath).send_keys(addAttr)

            elif action == "select" and addAttr != "":
                logger.debug(">>>>> start SELECT option index - {0}".format(str(addAttr)), extra=LOG_HEAD)
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    select = Select(driver.find_element_by_xpath(xpath))
                    select.select_by_index(int(addAttr))
                logger.debug(">>>>> end SELECT option index - {0}".format(str(addAttr)), extra=LOG_HEAD)

            logger.debug(">>>>> EXIT after executing step {0}.{1} action {2}".format(str(stepSeq), str(stepSeqSub), action), extra=LOG_HEAD)

            if stepSeq == "1" and stepSeqSub == "0":
                sessionId = self.getSessionId()

                if sessionId == "-" or sessionId == "" or sessionId == None:
                    logger.error("***** Session ID is NOT valid, aborting script!! *****", extra=LOG_HEAD)
                    self.tearDown();
                else:
                    logger.info("user session id: %s", sessionId, extra=LOG_HEAD)

            logger.debug(">>>>> BEGIN capturing a screenshot of the current page", extra=LOG_HEAD)
            with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                driver.save_screenshot(
                  RELATIVE_PATH + '/' 
                  + OUTPUT_FILE_HEAD + "_" 
                  + stepSeq + "-" 
                  + stepSeqSub + "_" 
                  + stepName + ".png"
                )
            logger.debug(">>>>> END capturing the screenshot of the current page", extra=LOG_HEAD)

        except TimeoutException, err:
            exception = "TimeoutException" 
            Error_Message = "RequestTime exceeded SLA time " + str( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )
            final_exception = exception
            
            if uri == "":
                uri = stepName # an alternative to set the URL when its empty 

            override_max_time = ( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )
            override_expensive_url = uri 
            logger.error("timeout: request time exceeded SLA time (%s) seconds [%s]", str(SYSTEM_SLA_REQUEST_TIME_THRESHOLD), getFrame(), extra=LOG_HEAD)

        if stepSeqSub != "0" and exception == None:
            return

        global statusCode, ProcessEndOfStep, errCount, expensiveURL, maxTime, stepTime 

        stepStarted = False
        endTime = time.time() * 1000
        ProcessEndOfStep = True
        maxTime = 0         
        domContentLoadedTime = 0
        fullyLoadedTime = 0

        if exception == None:
            logger.debug(">>>>> I will now try to capture the pageload times, but could take long on a slow site", extra=LOG_HEAD)

            try:
                with timeout(seconds=SYSTEM_SLA_REQUEST_TIME_THRESHOLD):
                    while ( domContentLoadedTime <= 0 or fullyLoadedTime <= 0 ):                        
                        if domContentLoadedTime <= 0:
                            domContentLoadedTime = driver.execute_script("return window.performance.timing.domContentLoadedEventEnd - window.performance.timing.navigationStart")
                        if fullyLoadedTime <= 0:
                            fullyLoadedTime = driver.execute_script("return window.performance.timing.loadEventEnd - window.performance.timing.navigationStart")

            except TimeoutException, err:
                logger.error("timeout: wait time to loadEventEnd() exceeded time (%s) seconds [%s]", str(SYSTEM_SLA_REQUEST_TIME_THRESHOLD), getFrame(), extra=LOG_HEAD)

            if fullyLoadedTime >= ( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 ) or fullyLoadedTime <= 0:
                exception = "TimeoutException" 
                Error_Message = "RequestTime exceeded SLA time " + str( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )
                final_exception = exception
                override_max_time = ( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )
                override_expensive_url = uri 

            if domContentLoadedTime <= 0:
                domContentLoadedTime = ( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )

            if fullyLoadedTime <= 0:
                fullyLoadedTime = ( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )                

            if uri == "":
                uri = stepName # an alternative to set the URL when its empty 

        
        logger.debug(">>>>> now I'm registering the step time", extra=LOG_HEAD)
        if fullyLoadedTime > 0:
            stepTime = fullyLoadedTime
        else:
            if timeoutExceptionPatter.match( exception ): # TimeoutException
                logger.debug(">>>>> setting the FullyLoaded time to be REQUEST SLA threashold!!", extra=LOG_HEAD)
                stepTime = ( SYSTEM_SLA_REQUEST_TIME_THRESHOLD * 1000 )
            else:
                logger.debug(">>>>> the FullyLoaded time is a negative number!!", extra=LOG_HEAD)
                stepTime = -1

        logger.debug("[%2s.%s] %15s : DOMContentLoaded = %10s, FullyLoaded = %10s" %(stepSeq, stepSeqSub, stepName, str(domContentLoadedTime), str(fullyLoadedTime)), extra=LOG_HEAD)

        logger.debug(">>>>> I will now start processing the HAR file", extra=LOG_HEAD)

        global pageAssets, glAssetCount

        for ent in proxi.har['log']['entries']:
            currRequest += 1

            if ProcessEndOfStep == True:
                statusCode = str(proxi.har['log']['entries'][0]['response']['status'])
            if ent['response']['status'] > 399:
                errCount += 1
            if maxTime < ent['time']:
                maxTime = ent['time']
                if len(ent['request']['url']) > 200:
                    expensiveURL = (ent['request']['url'])[:300]
                else:
                    expensiveURL = ent['request']['url']

            byteSize = 0
            byteSize = ent['response']['headersSize'] + ent['response']['bodySize']
            numRequests += 1
            
            if byteSize > 0:
                total_byteSize += byteSize

            #Check for assets in the page requested
            if 'mimeType' not in ent['response']['content']:
                continue

            # Only deal with assets when the mimeType is set
            glAssetCount += 1
            asset = str(ent['response']['content']['mimeType']) 
            tag = "other"

            if RE_JAVASCRIPT.match(asset):
                tag = "javascript"
            elif RE_CSS.match(asset):
                tag = "css"
            elif RE_IMAGE.match(asset):
                tag = "image"
            elif RE_HTML.match(asset):
                tag = "html"

            if tag in pageAssets: # if the page tag exist in the dictionary
               if 'count' in pageAssets[ tag ]:
                    pageAssets[ tag ]['count'] += 1
               else:
                    pageAssets[ tag ]['count'] = 1

               if 'size' in pageAssets[ tag ]:
                  if byteSize > 0:
                      pageAssets[ tag ]['size'] += byteSize
               else:
                  if byteSize > 0:
                      pageAssets[ tag ]['size'] = byteSize
                  else:
                      pageAssets[ tag ]['size'] = 0
            
            else: # if the page tag does not exist in the dictionary
               pageAssets[ tag ] = dict()
               pageAssets[ tag ]['count'] = 1

               if  byteSize > 0:
                  pageAssets[ tag ]['size'] = byteSize
               else:
                  pageAssets[ tag ]['size'] = 0


        if stepTime >= ( SYSTEM_SLA_PAGE_TIME_THRESHOLD * 1000 ) and exception == None:
            exception = "TimeoutException"
            Error_Message = "PageTime exceeded SLA time " + ( SYSTEM_SLA_PAGE_TIME_THRESHOLD * 1000 )
            final_exception = exception

        if requestTimeErrPattern.match( Error_Message ): # RequestTimeout
            maxTime = override_max_time
            expensiveURL = override_expensive_url

        elif pageTimeErrPattern.match( Error_Message ): # PageTimeOut
            try:
                raise TimeoutException
            except TimeoutException, err:
                exception = "TimeoutException"
                Error_Message = "PageTime exceeded SLA time " + str( SYSTEM_SLA_PAGE_TIME_THRESHOLD * 1000 )
                final_exception = exception
                logger.warning("timeout: page time exceeded SLA time (%s) seconds [%s]", str(SYSTEM_SLA_PAGE_TIME_THRESHOLD), getFrame(), extra=LOG_HEAD)

        ProcessEndOfStep = False
        logger.debug(">>>>> processing the HAR file is now complete", extra=LOG_HEAD)

        self.send_step_time(stepSeq, stepSeqSub, stepName)

        if exception != None: # and not Navigation timeout
            logger.error("********* %s occurred. aborting user journey :( ********* \n[%s]", exception, getFrame(), extra=LOG_HEAD)
            time.sleep(SYSTEM_SLEEP_TIME_BEFORE_TERMINATE)
            journey_status = JOURNEY_STATUS_FAILED + final_exception
            self.send_journey_time() 
            self.tearDown()

        logger.info("sleeping for %s seconds before next step", str(SYSTEM_THINK_TIME_BETWEEN_STEPS), extra=LOG_HEAD)
        time.sleep(SYSTEM_THINK_TIME_BETWEEN_STEPS)


    def test_userJourney(self):

        global journey_time, journey_status, final_exception
        global EXIT_STATUS_SUCCESS

        # user journey execution steps begin heree
        sortedSeq = sorted(steps, key=lambda x: int(x))

        for i in sortedSeq:
            #print "executig step : " + str(steps[i].seq) + "." + str(steps[i].seq_sub) + " : " + str(steps[i].name) + " : " +  str(steps[i].xpath_attr)
            self.execute_step(steps[i].method, steps[i].seq, steps[i].seq_sub, steps[i].name, steps[i].url, steps[i].xpath, steps[i].xpath_attr, steps[i].tls)
        
        if final_exception != None:
            journey_status = JOURNEY_STATUS_FAILED + final_exception
        else:
            journey_status = JOURNEY_STATUS_PASSED

        self.send_journey_time()

        # user journey execution steps end heree
        logger.info("sleeping for %s seconds before terminating script", str(SYSTEM_SLEEP_TIME_BEFORE_TERMINATE), extra=LOG_HEAD)
        time.sleep(SYSTEM_SLEEP_TIME_BEFORE_TERMINATE)
        logger.info("------------ End of SUCCESSFUL execution ------------", extra=LOG_HEAD)
        self.tearDown( EXIT_STATUS_SUCCESS )      
 

    def is_element_present(self, how, what):
        try: self.driver.find_element(by=how, value=what)
        except NoSuchElementException, e: return False
        return True
    

    def is_alert_present(self):
        try: self.driver.switch_to_alert()
        except NoAlertPresentException, e: return False
        return True
    

    def close_alert_and_get_its_text(self):
        try:
            alert = self.driver.switch_to_alert()
            alert_text = alert.text
            if self.accept_next_alert:
                alert.accept()
            else:
                alert.dismiss()
            return alert_text
        finally: self.accept_next_alert = True
    

    def tearDown(self, exitCode = 1):
        global proxi, driver, EXIT_STATUS_CODE       
        EXIT_STATUS_CODE = exitCode

        #either the proxi or the driver is None:
        if driver != None or proxi != None:
            try:
                logger.debug(">>>>> I will now try to release resources <<<<<<", extra=LOG_HEAD)
                
                if driver != None:
                    logger.debug(">>>>>>>> releasing resources held by the webdriver....", extra=LOG_HEAD)
                    driver.quit()
                    driver = None
                
                if proxi != None:
                    logger.debug(">>>>>>>> releasing resources held by the proxy....", extra=LOG_HEAD)
                    proxi.close()
                    proxi = None

            except:
                logger.warning("error while doing the cleanup in tearDown()", extra=LOG_HEAD)
                if EXIT_STATUS_CODE != 0:
                    sendExitStatus( EXIT_STATUS_CODE )
                else:
                    sendExitStatus( EXIT_STATUS_SUCCESS )

            if EXIT_STATUS_CODE != 0:
                logger.info("****** End Of Execution - Journey FAILED ", extra=LOG_HEAD)
            else:
                logger.info("****** End Of Execution - Journey SUCCESSFUL ", extra=LOG_HEAD)

            sendExitStatus( EXIT_STATUS_CODE )


    def send_step_time(self, stepSeq, stepSeqSub, stepName):

        # Wrap up and send pageweight stats to graylog
        global total_byteSize, numRequests, statusCode, errCount, expensiveURL, maxTime, stepTime, journey_time, expensive_step, max_step_time, total_err_count

        har_data = json.dumps(proxi.har, indent=4)
        try:
            save_har = open(RELATIVE_PATH + '/' + OUTPUT_FILE_HEAD + "_" + stepSeq + "-" + stepSeqSub + "_" + stepName + ".har", 'w')
            save_har.write(har_data)
            save_har.close()

        except IOError as e:
            logger.error("I/O error({0}): {1} {2}]".format(e.errno, e.strerror, getFrame()), extra=LOG_HEAD)
            self.tearDown()

        if total_byteSize >= 1048576:
            pageSize = total_byteSize / (1024*1024*1.00)
            sizeUnit = "MBytes"

        elif total_byteSize >= 1024:
            pageSize = total_byteSize / (1024*1.00)
            sizeUnit = "KBytes"

        else:
            pageSize = total_byteSize
            sizeUnit = "bytes"

        global pageAssets, glAssetCount
        firstPair = 0
        all_assets = ""

        for i in (pageAssets.keys()):
            countAndSize = str(i) + "=" + str(pageAssets[i]['count']) + "@" + str(pageAssets[i]['size'])
            if firstPair == 0:
                all_assets =  countAndSize
                firstPair = 1
            else:
                all_assets += ";" + countAndSize

        logger.info("total page weight is %s bytes (%s %s)", total_byteSize, "{0:.2f}".format(pageSize), sizeUnit, extra=LOG_HEAD)
	    # graylog entry should be with hostname of domain only evenif different store is present
        curl_cmd = (   
            "curl -k -XPOST " + SYSTEM_GRAYLOG_REST_URL + 
            ' -d \'{ "host":"' + SYSTEM_WEB_DOMAIN_URL + 
            '", "short_message":"Synthetic User Journey", "message_type":"PageWeight", "journey_name":"' + 
            SYSTEM_JOURNEY_NAME + '", "step_seq":"' + 
            stepSeq + '", "step_sub":"' + stepSeqSub + 
            '", "step_name":"' + stepName + '", "byte_size":' + 
            str(total_byteSize) + ',"status_code":"' + statusCode + 
            '", "error_count": ' + str(errCount) + ', "request_count":' +
            str(numRequests) + ', "user_session":"' + sessionId + 
            '", "assets":"' + str(all_assets) + '", "total_assets":' + str(glAssetCount) +
            ', "expensive_url":"' + urllib.quote(expensiveURL, safe='') + 
            '", "max_time": ' + str(maxTime) + ', "step_time": ' + 
            str(stepTime) + ', "exception": "' + str(exception) + 
            '", "error_message":"' + Error_Message + '" }\''
        )

        logger.debug(">>>>> page stats: %s", curl_cmd, extra=LOG_HEAD)

        if stepTime > max_step_time:
            max_step_time = stepTime
            expensive_step = stepName

        journey_time += stepTime
        total_err_count += errCount   

        statusCode     = "-"
        errCount       = 0    
        total_byteSize = 0
        numRequests    = 0
        expensiveURL   = "-"
        maxTime        = 0
        stepTime       = 0
        pageAssets.clear()
        glAssetCount   = 0

        try:
            logger.info("sending step data to Graylog @ %s", SYSTEM_GRAYLOG_REST_URL, extra=LOG_HEAD)
            rv = os.system(curl_cmd)
            if rv == 0:
                logger.info("******* step data SENT Successfully *******", extra=LOG_HEAD)
            else:
                logger.error("FAILED to send step data to Graylog!", extra=LOG_HEAD)
            
        except Exception, err:
            logger.error("error while sending stats to Graylog @ %s [%s]", SYSTEM_GRAYLOG_REST_URL, getFrame(), extra=LOG_HEAD)
            pass


    def send_journey_time(self):

        curl_cmd = (
            "curl -k -XPOST " + SYSTEM_GRAYLOG_REST_URL + 
            ' -d  \'{ "host":"' + SYSTEM_WEB_DOMAIN_URL + 
            '", "short_message":"Synthetic User Journey", "message_type":"JourneySummary", "journey_name": "' + 
            SYSTEM_JOURNEY_NAME + '", "user_session": "' + sessionId + 
            '", "journey_time": ' + str(journey_time) + ', "expensive_step": "' + 
            expensive_step + '", "max_time": ' + str(max_step_time) + ', "total_errors": ' + 
            str(total_err_count) + ', "status": "' + journey_status + '" }\''
        )

        try:
            logger.info("sending journey data to Graylog @ %s", SYSTEM_GRAYLOG_REST_URL, extra=LOG_HEAD)
            logger.debug(">>>>> journey stats: %s", curl_cmd, extra=LOG_HEAD)
            rv = os.system(curl_cmd)
            if rv == 0:
                logger.info("******* journey data SENT Successfully  *******", extra=LOG_HEAD)
            else:
                logger.error("FAILED to send journey summary to Graylog!", extra=LOG_HEAD)

        except Exception, err:
            logger.error("error while sending stats to Graylog @ %s [%s]", SYSTEM_GRAYLOG_REST_URL, getFrame(), extra=LOG_HEAD)
            pass


def usage():
    print ("%s\n    -h, --help\n    -c configfile or --config=<configfile>\n%s" %(__file__, "Note: config file path should be relative to the script path"))


# method that does the initiallisation and runs the test
def init(argv):

    global RELATIVE_PATH

    try:
        opts, args = getopt.getopt(argv,"hc:",["help", "config="])
        cmd_line_args_found = False

        for opt, arg in opts:
            if opt in ("-h", "--help"):
                cmd_line_args_found = True
                usage()
                sendExitStatus()

            elif opt == '-c' or opt == "--config":
                cmd_line_args_found = True
                RELATIVE_PATH = SYSTEM_LOG_FILE_PATH + "/" + arg
                configurePath()
                # Now run the user journey
                out = SyntheticUserJourney('test_userJourney')()


        if cmd_line_args_found == False:
            print "Oops! sorry mate, I didn't understand that\n"
            usage()
            sendExitStatus()

    except getopt.GetoptError:
        usage()
        sendExitStatus()


# Global declarations
user_agent_str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.11; rv:43.0) Gecko/20100101 Firefox/43.0; TryzensUXBot"
capabilities = DesiredCapabilities.FIREFOX.copy()
capabilities['general.useragent.override'] = user_agent_str
driver = None
proxi = None

# User variables
SYSTEM_WEB_DOMAIN = "localhost"
SYSTEM_WEB_DOMAIN_URL = "localhost"
SYSTEM_GRAYLOG_REST_URL = "https://127.0.0.1:12280/gelf"
SYSTEM_SELENIUM_HUB_URL = "http://127.0.0.1:4444/wd/hub"
SYSTEM_BROWSER_PROXY = "127.0.0.1:9090"
SYSTEM_JOURNEY_NAME = "GuestBrowseSite"
SYSTEM_SLEEP_TIME_BEFORE_TERMINATE = 5
SYSTEM_THINK_TIME_BETWEEN_STEPS = 1
SYSTEM_SLA_REQUEST_TIME_THRESHOLD = 30
SYSTEM_SLA_PAGE_TIME_THRESHOLD = 60
WEBDRIVER_PROXY_TIMEOUT = 60

PLATFORM_SESSION_IDENTIFIER = [
    'sid', 
    'JSESSIONID', 
    'CACHED_FRONT_FORM_KEY', 
    'PHPSESSID'
]

requestTimeErrPattern    = re.compile(r"^RequestTime")
pageTimeErrPattern       = re.compile(r"^PageTime")
naviagtionTimeErrPattern = re.compile(r"^Navigation")
timeoutExceptionPatter   = re.compile(r"^TimeoutException")

# Other variables
OUTPUT_FILE_HEAD = SYSTEM_WEB_DOMAIN.replace("/", "_")
startTime = 0
endTime = 0

sessionId = "-"
maxTime = 0
stepTime = 0
pageSize = 0
numRequests = 0
statusCode = "-"
errCount = 0
expensiveURL = "-"
exception = None 

sizeUnit = "Bytes"
total_byteSize = 0
pageAssets = dict()
RE_JAVASCRIPT = re.compile(r".*?javascript")
RE_CSS = re.compile(r".*?css")
RE_IMAGE = re.compile(r".*?image")
RE_HTML = re.compile(r".*?html")
glAssetCount = 0

currRequest = 0
stepStarted = False

JOURNEY_STATUS_NOT_STARTED="NOT_STARTED"
JOURNEY_STATUS_FAILED="FAILED: "
JOURNEY_STATUS_PASSED="SUCCESSFUL"
journey_status = JOURNEY_STATUS_NOT_STARTED
final_exception = None
expensive_step = "-"
max_step_time = 0
total_err_count = 0
journey_time = 0
Error_Message = ""
ProcessEndOfStep = False

# The main entry point in the script
if __name__ == "__main__":
    init(sys.argv[1:])


