import os
import io
import boto3
import json
import csv
import email
from sms_spam_classifier_utilities import one_hot_encode
from sms_spam_classifier_utilities import vectorize_sequences

# grab environment variables
ENDPOINT_NAME = os.environ['ENDPOINT_NAME']
runtime= boto3.client('runtime.sagemaker')
vocabulary_length = 9013
CHARSET = "UTF-8"
s3 = boto3.client('s3')
ses = boto3.client('ses', region_name='us-east-1')

def parseEmailBody(msg):
    body = ''
    if msg.is_multipart():
        for p in msg.get_payload():
            body += p.get_payload()
            break
    else:
        body += msg.get_payload(decode=True)
    return body.replace('\r', ' ').replace('\n',' ')


def getEmail(event):
    print("My Event is : ", event)
    file_obj = event["Records"][0]
    filename = str(file_obj["s3"]['object']['key'])
    bucketname = str(file_obj["s3"]['bucket']['name'])
    print("filename: ", filename)
    fileObj = s3.get_object(Bucket = bucketname, Key=filename)
    print("file has been gotten!")
    return email.message_from_bytes(fileObj['Body'].read())


def respondToEmail(msg, spamResult):
    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = ("We received your email sent at {received} with the subject {subject}\r\n"
                 "Here is a 240 character sample of the email body:\r\n {body}\r\n"
                 "The email was categorized as {classification} with a {confidenceScore}% confidence"
                 )

    label = 'Spam' if (spamResult['predicted_label'][0][0] == 1.0) else 'Not Spam'
    percentage = round(spamResult['predicted_probability'][0][0]*100, 2)
    score = percentage if (spamResult['predicted_label'][0][0] == 1.0) else (100 - percentage)
    #Provide the contents of the email.
    response = ses.send_email(
        Destination={
            'ToAddresses': [
                msg['From'][msg['From'].find('<') + 1: msg['From'].find('>')],
            ],
        },
        Message={
            'Body': {
                'Text': {
                    'Charset': CHARSET,
                    'Data': BODY_TEXT.format(received=msg['Received'][msg['Received'].find(';') + 2:],
                                             subject=msg['Subject'],
                                             body=parseEmailBody(msg),
                                             classification=label,
                                             confidenceScore=score
                                             ),
                },
            },
            'Subject': {
                'Charset': CHARSET,
                'Data': msg['Subject'],
            },
        },
        Source='Haroon Sherjan <haroon@sherjan.net>',
    )


def checkForSpam(body):
    one_hot_test_messages = one_hot_encode([body], vocabulary_length)
    encoded_test_messages = vectorize_sequences(one_hot_test_messages, vocabulary_length)
    response = runtime.invoke_endpoint(EndpointName=ENDPOINT_NAME,
                                       ContentType='application/json',
                                       Body=json.dumps(encoded_test_messages.tolist()))

    return json.loads(response["Body"].read().decode())


def lambda_handler(event, context):
    msg = getEmail(event)
    body = parseEmailBody(msg)
    print(body)
    spamResult = checkForSpam(body)
    print(spamResult)
    respondToEmail(msg, spamResult)
