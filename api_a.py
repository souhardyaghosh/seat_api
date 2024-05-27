from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from urllib import request as url_request, parse
import re
import json
import time
from PIL import Image
from io import BytesIO
import requests
import ssl

app = Flask(__name__)

# Constants
OCR_API_KEY = 'K83337641288957'
OCR_API_URL = 'https://api.ocr.space/parse/image'

# Disable SSL certificate verification globally
requests.packages.urllib3.disable_warnings()
requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += 'HIGH:!DH:!aNULL'
try:
    requests.packages.urllib3.contrib.pyopenssl.DEFAULT_SSL_CIPHER_LIST += 'HIGH:!DH:!aNULL'
except AttributeError:
    # no pyopenssl support used / needed / available
    pass

def get_cookies(headers):
    headers = str(headers).split("\n")
    cookies = ""
    for item in headers:
        if item.startswith("Set-Cookie"):
            cookies += item.split(" ")[1]
    return cookies

def show_captcha():
    global cookies, answer
    ts = int(time.time() * 1000)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
    }
    req = url_request.Request("http://www.indianrail.gov.in/enquiry/captchaDraw.png?" + str(ts), headers=headers)
    
    # Disable SSL certificate verification for urllib.request
    context = ssl._create_unverified_context()
    
    with url_request.urlopen(req, context=context) as res:
        data = res.read()
        cookies = get_cookies(res.headers)
    img = Image.open(BytesIO(data))

    # Call the OCR API
    result = ocr_space_file(img)
    text = result['ParsedResults'][0]['ParsedText']
    obj = re.search(r'^(\s*\d+\s*[-+]\s*\d+\s*)=.*$', text)
    if obj:
        eq = obj.group(1)
        answer = eval(eq)
        return answer
    else:
        return None

def ocr_space_file(image):
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_str = buffered.getvalue()
    
    response = requests.post(
        OCR_API_URL,
        files={"file": ("captcha.png", img_str, "image/png")},
        data={"apikey": OCR_API_KEY, "language": "eng"},
        verify=False  # Disable SSL certificate verification for requests
    )
    return response.json()

def get_train_details(train_number, src_long, dest_long, src, dest, date):
    global cookies, answer
    ts = int(time.time() * 1000)
    headers = {
        "Cookie": cookies,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
    }
    data = {
        "inputCaptcha": answer,
        "dt": date.strftime("%d-%m-%Y"),
        "sourceStation": src_long,
        "destinationStation": dest_long,
        "flexiWithDate": "n",
        "inputPage": "TBIS",
        "language": "en",
        "_": ts
    }
    data = parse.urlencode(data).encode()
    url = "http://www.indianrail.gov.in/enquiry/CommonCaptcha?" + data.decode('ascii')
    req = url_request.Request(url, headers=headers)
    
    # Disable SSL certificate verification for urllib.request
    context = ssl._create_unverified_context()
    
    with url_request.urlopen(req, context=context) as res:
        trains = json.loads(res.read().decode('ascii'))
    
    for item in trains['trainBtwnStnsList']:
        if item['trainNumber'] == train_number and item['fromStnCode'] == src and item['toStnCode'] == dest:
            return {
                "train_number": item['trainNumber'],
                "train_name": item['trainName'],
                "departure_time": item['departureTime'],
                "arrival_time": item['arrivalTime'],
                "train_type": item['trainType']
            }
    return None

def get_availability(train_number, src, dest, date, class1, train_type):
    global cookies, answer
    ts = int(time.time() * 1000)
    headers = {
        "Cookie": cookies,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
    }
    data = {
        "inputCaptcha": answer,
        "inputPage": "TBIS_CALL_FOR_FARE",
        "trainNo": train_number,
        "dt": date.strftime("%d-%m-%Y"),
        "sourceStation": src,
        "destinationStation": dest,
        "classc": class1,
        "quota": "GN",
        "traintype": train_type,
        "language": "en",
        "_": ts
    }
    data = parse.urlencode(data).encode()
    url = "http://www.indianrail.gov.in/enquiry/CommonCaptcha?" + data.decode('ascii')
    req = url_request.Request(url, headers=headers)
    
    # Disable SSL certificate verification for urllib.request
    context = ssl._create_unverified_context()
    
    with url_request.urlopen(req, context=context) as res:
        d = res.read()
        avail = json.loads(d.decode('utf8'))
    
    try:
        return avail['avlDayList'][0]['availablityStatus'], avail['totalCollectibleAmount']
    except:
        return "Error", 0

@app.route('/check_availability', methods=['GET'])
def check_availability():
    src = request.args.get('src')
    dest = request.args.get('dest')
    class1 = request.args.get('class')
    date_str = request.args.get('date')
    train_number = request.args.get('train')
    date = datetime.strptime(date_str, '%d-%m-%Y')
    
    # Fetch stations
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:86.0) Gecko/20100101 Firefox/86.0"
    }
    req = url_request.Request("http://www.indianrail.gov.in/enquiry/FetchAutoComplete", headers=headers)
    
    # Disable SSL certificate verification for urllib.request
    context = ssl._create_unverified_context()
    
    with url_request.urlopen(req, context=context) as res:
        stations = json.loads(res.read().decode('ascii'))
    
    src_long = next(item for item in stations if item.endswith(" " + src))
    dest_long = next(item for item in stations if item.endswith(" " + dest))
    
    answer = show_captcha()
    if not answer:
        return jsonify({"error": "Failed to solve captcha"}), 500
    
    train_details = get_train_details(train_number, src_long, dest_long, src, dest, date)
    if not train_details:
        return jsonify({"error": "Train not found"}), 404
    
    availability, fare = get_availability(train_number, src, dest, date, class1, train_details['train_type'])
    
    response = {
        "TRAIN NAME": train_details["train_name"],
        "TRAIN NUMBER": train_details["train_number"],
        "DEPT": train_details["departure_time"],
        "ARR": train_details["arrival_time"],
        "AVAILABILITY": availability,
        "FARE": fare
    }
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=True)
