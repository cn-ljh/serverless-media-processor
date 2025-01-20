import boto3
import datetime
import hashlib
import hmac
from urllib.parse import quote, urlencode

def sign(key, msg):
    return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

def getSignatureKey(key, dateStamp, regionName, serviceName):
    kDate = sign(('AWS4' + key).encode('utf-8'), dateStamp)
    kRegion = sign(kDate, regionName)
    kService = sign(kRegion, serviceName)
    kSigning = sign(kService, 'aws4_request')
    return kSigning

def generate_signed_url():
    # Get credentials
    session = boto3.Session()
    credentials = session.get_credentials().get_frozen_credentials()
    
    # Request details
    method = 'POST'
    service = 'execute-api'
    region = 'cn-northwest-1'
    host = ''
    endpoint = f'https://{host}/prod/doc/doc.doc'
    canonical_uri = '/prod/doc/doc.doc'
    query_strings = "operations=convert,target_pdf,source_doc"

    # Time details
    t = datetime.datetime.utcnow()
    amzdate = t.strftime('%Y%m%dT%H%M%SZ')
    datestamp = t.strftime('%Y%m%d')

    
    # Generate query parameters including auth params
    query_params = {
        'operations': query_strings,
        'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
        'X-Amz-Credential': f"{credentials.access_key}/{datestamp}/{region}/{service}/aws4_request",
        'X-Amz-Date': amzdate,
        'X-Amz-SignedHeaders': 'host'
    }
    
    if credentials.token:
        query_params['X-Amz-Security-Token'] = credentials.token
    
    # Create canonical query string
    canonical_querystring = '&'.join([f"{quote(k, safe='')}={quote(v, safe='')}" 
                                    for k, v in sorted(query_params.items())])
    
    # Create canonical headers
    canonical_headers = f'host:{host}\n'
    
    # Create payload hash
    payload_hash = hashlib.sha256(''.encode('utf-8')).hexdigest()
    
    # Create canonical request
    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\nhost\n{payload_hash}"
    
    # Create string to sign
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = f"{algorithm}\n{amzdate}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    
    # Calculate signature
    signing_key = getSignatureKey(credentials.secret_key, datestamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # Add signature to query parameters
    query_params['X-Amz-Signature'] = signature
    
    # Create final query string
    final_querystring = '&'.join([f"{quote(k, safe='')}={quote(v, safe='')}" 
                                 for k, v in sorted(query_params.items())])
    
    # Create final URL
    final_url = f"{endpoint}?{final_querystring}"
    
    print("\nComplete signed URL:")
    print("===================")
    print(final_url)
    
    return final_url

if __name__ == '__main__':
    generate_signed_url()
