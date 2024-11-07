import mozserial
import mozsnappy
import json

with open('15unsnapped', 'rb') as f:
    yes = mozserial.Reader(f)
    parsed = yes.read()
    with open('15JSON.json', 'a') as f2:
        f2.write('[')
        for key in parsed:
            try:
                f2.write(json.dumps({key : parsed[key]}))
                f2.write(',')
            except Exception as e:
                print(e)
                print(key, parsed[key])
                continue
        f2.write(']')