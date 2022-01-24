# -*- coding: utf-8 -*-

# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License"). You may not use this file except in
# compliance with the License. A copy of the License is located at
#
#    http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific
# language governing permissions and limitations under the License.

import boto3
import json
import paho.mqtt.client as paho
from alexa.skills.smarthome import AlexaResponse
import time

aws_dynamodb = boto3.client('dynamodb')

objs = {}

def lambda_handler(request, context):

    # Dump the request for logging - check the CloudWatch logs
    print('lambda_handler request  -----')
    print(json.dumps(request))

    if context is not None:
        print('lambda_handler context  -----')
        print(context)

    # Validate we have an Alexa directive
    if 'directive' not in request:
        aer = AlexaResponse(
            name='ErrorResponse',
            payload={'type': 'INVALID_DIRECTIVE',
                     'message': 'Missing key: directive, Is the request a valid Alexa Directive?'})
        return send_response(aer.get())

    # Check the payload version
    payload_version = request['directive']['header']['payloadVersion']
    if payload_version != '3':
        aer = AlexaResponse(
            name='ErrorResponse',
            payload={'type': 'INTERNAL_ERROR',
                     'message': 'This skill only supports Smart Home API version 3'})
        return send_response(aer.get())

    # Crack open the request and see what is being requested
    name = request['directive']['header']['name']
    namespace = request['directive']['header']['namespace']

    # Handle the incoming request from Alexa based on the namespace

    if namespace == 'Alexa.Authorization':
        if name == 'AcceptGrant':
            # Note: This sample accepts any grant request
            # In your implementation you would use the code and token to get and store access tokens
            grant_code = request['directive']['payload']['grant']['code']
            grantee_token = request['directive']['payload']['grantee']['token']
            aar = AlexaResponse(namespace='Alexa.Authorization', name='AcceptGrant.Response')
            return send_response(aar.get())

    if namespace == 'Alexa.Discovery':
        if name == 'Discover':
            discover()
            adr = AlexaResponse(namespace='Alexa.Discovery', name='Discover.Response')
            capability_alexa = adr.create_payload_endpoint_capability()
            capability_alexa_powercontroller = adr.create_payload_endpoint_capability(
                interface='Alexa.PowerController',
                supported=[{'name': 'powerState'}])
            capability_alexa_brightnesscontroller = adr.create_payload_endpoint_capability(
                interface='Alexa.BrightnessController',
                supported=[{'name': 'brightness'}])
            for key, value in objs.items():
                if not value['type'] == 'binary-output' and not value['type'] == 'analog-output':
                    continue
                capab = []
                if value['type'] == 'binary-output':
                    capab=[capability_alexa, capability_alexa_powercontroller]
                elif value['type'] == 'analog-output':
                    capab=[capability_alexa, capability_alexa_powercontroller, capability_alexa_brightnesscontroller]
                adr.add_payload_endpoint(
                    display_categories=['LIGHT'],
                    friendly_name=str(value['properties']['description']).replace("b", "").replace("'", ""),
                    description="test",
                    manufacturer_name="Sauter",
                    endpoint_id= key.replace("/", "."),
                    capabilities=capab)
            return send_response(adr.get())

    if namespace == 'Alexa.PowerController':
        # Note: This sample always returns a success response for either a request to TurnOff or TurnOn
        endpoint_id = request['directive']['endpoint']['endpointId']
        power_state_value = 'OFF' if name == 'TurnOff' else 'ON'
        correlation_token = request['directive']['header']['correlationToken']

        # Check for an error when setting the state
        state_set = set_device_state(endpoint_id=endpoint_id, state='powerState', value=power_state_value)
        if not state_set:
            return AlexaResponse(
                name='ErrorResponse',
                payload={'type': 'ENDPOINT_UNREACHABLE', 'message': 'Unable to reach endpoint database.'}).get()

        apcr = AlexaResponse(correlation_token=correlation_token)
        apcr.add_context_property(namespace='Alexa.PowerController', name='powerState', value=power_state_value)
        return send_response(apcr.get())
        
    if namespace == 'Alexa.BrightnessController':
        # Note: This sample always returns a success response for either a request to TurnOff or TurnOn
        endpoint_id = request['directive']['endpoint']['endpointId']
        power_state_value = 'OFF' if name == 'TurnOff' else 'ON'
        correlation_token = request['directive']['header']['correlationToken']

        # Check for an error when setting the state
        state_set = set_device_state(endpoint_id=endpoint_id, state='powerState', value=power_state_value)
        if not state_set:
            return AlexaResponse(
                name='ErrorResponse',
                payload={'type': 'ENDPOINT_UNREACHABLE', 'message': 'Unable to reach endpoint database.'}).get()

        apcr = AlexaResponse(correlation_token=correlation_token)
        apcr.add_context_property(namespace='Alexa.PowerController', name='powerState', value=power_state_value)
        return send_response(apcr.get())

def on_connect(client, userdata, flags, rc): 
    #print("Connected with result code {0}".format(str(rc)))  
    client.subscribe("sauter/ecos504/411000573341/status/#")

def on_message(client, userdata, msg): 
    global objs 
    #print("Message received-> " + msg.topic + " " + str(msg.payload))
    topic_elements = msg.topic.split("/")  
    topic_root = msg.topic.replace("/" + topic_elements[-1], "")

    if not topic_root in objs:
        obj = {
            "internal_id": topic_elements[-2],
            "type": topic_elements[-3],
            "properties": {}
        }
        obj["properties"][topic_elements[-2]] = msg.payload
        objs[topic_root] = obj
    else:
        objs[topic_root]["properties"][topic_elements[-1]] = msg.payload

def discover():
    client= paho.Client()
    client.on_connect = on_connect  
    client.on_message = on_message  

    client.username_pw_set('', '')
    client.connect('', 1883)
    startscan = time.time()
    while True:
        client.loop()
        if time.time() - startscan > 2:
            #print(objs)
            break

def send_response(response):
    # TODO Validate the response
    print('lambda_handler response -----')
    print(json.dumps(response))
    return response

def set_device_state(endpoint_id, state, value):
    client= paho.Client()
    client.username_pw_set('', '')
    client.connect('', 1883)
    endpoint_clean = endpoint_id.replace("/", ".").replace("status", "command")
    setvalue = "0"
    if value == "ON":
        setvalue = "100"
    result = client.publish("endpoint_clean", setvalue)
    status = result[0]
    if status == 0:
        return True
    else:
        return False
        
def set_device_percentage(endpoint_id, state, percentage):
    client= paho.Client()
    client.username_pw_set('', '')
    client.connect('', 1883)
    endpoint_clean = endpoint_id.replace("/", ".").replace("status", "command")
    result = client.publish("endpoint_clean", percentage)
    status = result[0]
    if status == 0:
        return True
    else:
        return False

def set_device_state_unused(endpoint_id, state, value):
    attribute_key = state + 'Value'
    response = aws_dynamodb.update_item(
        TableName='SampleSmartHome',
        Key={'ItemId': {'S': endpoint_id}},
        AttributeUpdates={attribute_key: {'Action': 'PUT', 'Value': {'S': value}}})
    print(response)
    if response['ResponseMetadata']['HTTPStatusCode'] == 200:
        return True
    else:
        return False
