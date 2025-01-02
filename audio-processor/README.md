# Audio Processor API

This Lambda function provides audio processing capabilities through API Gateway, supporting WAV to various format conversions with configurable parameters.

## API Endpoint

```
GET /audio/{key}
```

## Parameters

- `key`: The object key (path) of the audio file in S3 bucket
- `operations`: Query parameter specifying the audio operations to perform

## Supported Operations

### Convert (`convert`)
Converts WAV audio to different formats with various parameters.

Parameters:
- `ss_<milliseconds>`: Start time in milliseconds (optional)
  * Default: 0 (start from beginning)
  * Example: ss_10000 (start from 10 seconds)

- `t_<milliseconds>`: Duration in milliseconds (optional)
  * Default: 0 (until end)
  * Example: t_60000 (process 60 seconds)

- `f_<format>`: Output format (required)
  * Supported formats: mp3, aac, flac, oga, ac3, opus, amr
  * Example: f_mp3

- `ar_<rate>`: Sample rate in Hz (optional)
  * Supported rates: 8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000
  * Format-specific restrictions:
    - mp3: Up to 48kHz
    - opus: 8kHz, 12kHz, 16kHz, 24kHz, 48kHz only
    - ac3: 32kHz, 44.1kHz, 48kHz only
    - amr: 8kHz, 16kHz only
  * Example: ar_44100

- `ac_<channels>`: Number of audio channels (optional)
  * Range: 1-8
  * Format-specific restrictions:
    - mp3: 1-2 channels only
    - ac3: Up to 6 channels (5.1)
    - amr: Mono only (1 channel)
  * Example: ac_2

- `aq_<quality>`: Audio quality (optional)
  * Range: 0-100
  * Mutually exclusive with ab parameter
  * Example: aq_90

- `ab_<bitrate>`: Audio bitrate in bps (optional)
  * Range: 1000-10000000
  * Mutually exclusive with aq parameter
  * Example: ab_192000

- `abopt_<option>`: Bitrate option (optional)
  * Values:
    - 0: Always use target bitrate (default)
    - 1: Use source bitrate if lower than target
    - 2: Fail if source bitrate is lower
  * Example: abopt_1

- `adepth_<depth>`: Sample depth for FLAC (optional)
  * Values: 16 or 24
  * Only applicable when f=flac
  * Example: adepth_24

## Examples

1. Basic WAV to MP3 Conversion
```
GET /audio/example.wav?operations=convert,f_mp3
```

2. Convert to AAC with Specific Bitrate
```
GET /audio/example.wav?operations=convert,f_aac,ab_96000
```

3. Extract 60-second Segment Starting at 10 Seconds
```
GET /audio/example.wav?operations=convert,ss_10000,t_60000,f_mp3
```

4. High-Quality FLAC Conversion
```
GET /audio/example.wav?operations=convert,f_flac,ar_96000,adepth_24
```

5. Convert to Mono AAC with Sample Rate
```
GET /audio/example.wav?operations=convert,f_aac,ac_1,ar_44100,ab_64000
```

## Response

### Success Response
- Status Code: 200
- Body: Processed audio binary
- Headers:
  ```
  Content-Type: audio/[format]
  Cache-Control: public, max-age=3600
  ETag: [md5-hash]
  ```

### Error Response
- Status Code: 400/500
- Body:
  ```json
  {
    "error": "Error message"
  }
  ```

## Notes

- Input format must be WAV
- The function has a timeout of 300 seconds (5 minutes)
- Memory allocation is 1024MB
- Requires S3 bucket access for reading source files
- Uses ffmpeg for audio processing
- Audio files are cached for 1 hour (Cache-Control: public, max-age=3600)
- Parameters aq (quality) and ab (bitrate) are mutually exclusive
- Format-specific restrictions apply to sample rates and channel counts
