"""
This sample demonstrates a simple skill built with the Amazon Alexa Skills Kit.
The Intent Schema, Custom Slots, and Sample Utterances for this skill, as well
as testing instructions are located at http://amzn.to/1LzFrj6
For additional samples, visit the Alexa Skills Kit Getting Started guide at
http://amzn.to/1LGWsLG
"""

from __future__ import print_function
import urllib
import xml.etree.ElementTree as ET
import datetime
import json
import boto3
import botocore
from boto3.dynamodb.conditions import Key
import logging
logger = logging.getLogger()

def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print("event.session.application.applicationId=" +
          event['session']['application']['applicationId'])

    #Don't let anyone else's skill send requests to this lambda
    if (event['session']['application']['applicationId'] !=
             "amzn1.echo-sdk-ams.app.[application_id_goes_here]"):
         raise ValueError("Invalid Application ID")

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.info('got event{}'.format(event))

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    if event['request']['type'] == "LaunchRequest":
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == "IntentRequest":
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])


def on_session_started(session_started_request, session):
    """ Called when the session starts """

    print("on_session_started requestId=" + session_started_request['requestId']
          + ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they
    want
    """

    print("on_launch requestId=" + launch_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """

    print("on_intent requestId=" + intent_request['requestId'] +
          ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # Dispatch to your skill's intent handlers
    if intent_name == "WhensNextTrainIntent":
        return get_next_train(intent, session)
    elif intent_name == "SetFavoriteStationIntent":
        return set_favorite_station(intent, session)
    elif intent_name == "AMAZON.HelpIntent":
        return get_welcome_response()
    else:
        raise ValueError("Invalid intent")


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.
    Is not called when the skill returns should_end_session=true
    """
    print("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # add cleanup logic here

# --------------- Functions that control the skill's behavior ------------------


def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """

    session_attributes = {}
    card_title = "Welcome"
    
    #check if the user has a home station set up
    station_id, station_name = get_favorite_station(session)
    if station_id and station_name:
        speech_output = "Welcome to the CTA tracker. " \
                        "You can request the next train time by saying, " \
                        "when is the next northbound train"
    else:
        speech_output = "Welcome to the CTA tracker. " \
                        "What station are you interested in? " \
                        "You can say, I'm on the red line, sheridan station"
    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.
    reprompt_text = "Please ask for the next northbound train time by saying, " \
                    "when is the next northboud train"
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))

def get_favorite_station(session):
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('favorite_station')
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(session['user']['userId'])
    )
    station_id = None
    station_name = None
    if len(response['Items']) > 0:
        row = response['Items'][0]
        if 'station_id' in row and 'station_name' in row:
            station_id = response['Items'][0]['station_id']
            station_name = response['Items'][0]['station_name']
    return station_id, station_name

def match_station_name(user_station_name, actual_station_name):
    # TODO: make this more robust, obviously
    return user_station_name.upper() in actual_station_name.upper()

def deduplicate(inp):
  out = []
  for val in inp:
    if val not in out:
      out.append(val)
  return out

def get_line_abbr(user_line_name):
    colors = {'blue': 'BLUE',
        'brown': 'BRN',
        'green': 'G',
        'orange': 'O',
        'pink': 'P',
        'purple': 'Pnk',
        'red': 'RED',
        'yellow': 'Y'}
    return colors[user_line_name]
    
def set_favorite_station(intent, session):
    session_attributes = {}
    reprompt_text = None
    
    
    station_line = intent['slots']['StationLine']['value']
    station_name = intent['slots']['StationName']['value']
    
    #first, get all stations on the line
    
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('el_stations')
    line_abbr = get_line_abbr(station_line)
    fe = Key(line_abbr).eq('TRUE')
    pe = "MAP_ID, STATION_NAME"
    response = table.scan(
        FilterExpression=fe,
        ProjectionExpression=pe
    )
    
    #then check which station names match what the user said:
    matches = []
    for row in response['Items']:
        if match_station_name(station_name, row['STATION_NAME']):
            matches.append((row['MAP_ID'], row['STATION_NAME']))
    matches = deduplicate(matches)
    speech_output = json.dumps(matches)
    if len(matches) == 1:
        user_station_table = dynamodb.Table('favorite_station')
        response = user_station_table.put_item(
            Item={
                'user_id': session['user']['userId'],
                'station_id': matches[0][0],
                'station_name': matches[0][1]
            }
        )
        speech_output = "Saved your home station as " + matches[0][1] \
                        + ". To get arrival times, you can ask, " \
                        + "when is the next northbound train coming?"
    else:
        speech_output = "please try again " + str(len(matches))
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        intent['name'], speech_output, reprompt_text, should_end_session))

def set_direction(userId, direction):
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('last_direction')

    response = table.put_item(
        Item={
            'user_id': userId,
            'direction': direction
        }
    )
    return response

def get_last_direction(userId):
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('last_direction')
    direction = None
    
    response = table.query(
        KeyConditionExpression=Key('user_id').eq(userId)
    )
    if len(response['Items']) > 0:
        direction = response['Items'][0]['direction']
    return direction

def get_direction_text(direction):
    if direction == '1':
        return 'northbound'
    elif direction == '5':
        return 'southbound'
    else:
        raise ValueError("Invalid direction. Valid values are '1' (northbound) and '5' (southbound)")
        
def get_direction_nbr(direction):
    if direction == 'northbound':
        return '1'
    elif direction == 'southbound':
        return '5'
    else:
        return None

def get_minutes_text(interval):
    minutes_int = int(str(interval).split(':')[1])
    return str(minutes_int) + " minute" + ("s" if minutes_int!=1 else "")

def get_next_train_helper(station_id, station_name, direction):
    apiKey = "api_key_goes_here"
    u = urllib.urlopen('http://lapi.transitchicago.com/api/1.0/ttarrivals.aspx?key='+apiKey+'&mapid='+station_id+'&max=8')
    data = u.read()
    tree = ET.fromstring(data)
    times = []
    for eta in tree.findall('eta'):
        if eta.find('trDr').text == direction: #i.e., northbound
            prdt = datetime.datetime.strptime(eta.find('prdt').text, "%Y%m%d %H:%M:%S")
            arrT = datetime.datetime.strptime(eta.find('arrT').text, "%Y%m%d %H:%M:%S")
            times.append(arrT-prdt)
    num_trains = len(times)
    if num_trains == 0:
            speech_output = "No " + get_direction_text(direction) + " trains found."
    elif num_trains == 1:
        speech_output = "I only found one " + get_direction_text(direction) + " \
                        train for " + station_name + ". It arrives in " \
                        + get_minutes_text(times[0])
    elif num_trains == 2:
        speech_output = get_direction_text(direction) + " trains arriving at " \
                        + station_name + " in " \
                        + get_minutes_text(times[0]) \
                        + "and " + get_minutes_text(times[1])
    else:
        speech_output = get_direction_text(direction) + " trains arriving at " \
                        + station_name + " in " \
                        + get_minutes_text(times[0]) \
                        + ", " + get_minutes_text(times[1]) \
                        + ", and " + get_minutes_text(times[2])
    return speech_output

def get_next_train(intent, session):
    session_attributes = {}
    reprompt_text = None

    station = None
    direction = None
    
    userId = session['user']['userId']
    
    if 'value' in intent['slots']['Direction']:
        direction = get_direction_nbr(intent['slots']['Direction']['value'])
    if direction:
        set_direction(userId, direction)
    else:
        #user didn't specify a direction. first, assume they want the same as last time:
        direction = get_last_direction(userId)
    if direction:
        station_id, station_name = get_favorite_station(session)
        if station_id and station_name:
            speech_output = get_next_train_helper(station_id, station_name, direction)
            should_end_session = True
        else:
            speech_output = "Please set your home station first. " \
                            "You can say, I live at the blue line belmont station."
            should_end_session = False
    else:
        speech_output = "Please specify a direction. I'll remember it for next time. " \
                        "You can say, when is the next northbound train"
        should_end_session = False
        
    # Setting reprompt_text to None signifies that we do not want to reprompt
    # the user. If the user does not respond or says something that is not
    # understood, the session will end.
    return build_response(session_attributes, build_speechlet_response(
        intent['name'], speech_output, reprompt_text, should_end_session))

def format_time_to_train(interval):
    return str(int(str(interval).split(':')[1]))

# --------------- Helpers that build all of the responses ----------------------


def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': 'SessionSpeechlet - ' + title,
            'content': 'SessionSpeechlet - ' + output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }


def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }