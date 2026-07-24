import json
import glob
import os
import subprocess
from datetime import datetime, timezone, timedelta
from exif import Image

### 
### CUSTOMIZATION OPTIONS
###

# path to .json generated from exporting Location History
tf = open('Timeline.json')

# matches photo numbers and custom overrides to a particular lat long
# this mechanism is currently fuji filename format specific (DSCFXXXX.jpg)
custom_override = {
# "2678": (46.7869407, -121.7346464),
}

# path to your instance of EXIFTOOL
exiftool_path = ""
# path to your input images (must be .jpg)
input_path = ""
# path to your output images
output_path = ""
# timezone used by the camera
camera_tz = timezone(-timedelta(hours=7))

###
### SCRIPT BEGINS HERE
###

tf_j = json.load(tf)
idx = 0

# for every input image
for jpg in glob.glob(input_path + "*.jpg", recursive=True):

    # get current date and time from image EXIF
    f = open(jpg, 'rb')
    exif = Image(f)
    if 'datetime_original' in exif.list_all():

        gps_latititude = 0
        gps_longitude = 0

        tp_idx = 0
        act_idx = 0
        vi_idx = 0

        d_exif = datetime.strptime(exif.datetime_original, '%Y:%m:%d %H:%M:%S').replace(tzinfo=camera_tz)

        #
        # location history has three kinds of segments: visit, activity, and timelinePath.
        # march the index was forward for each kind of segment to the LAST segment which
        # starts before the picture was taken. 
        #
        while datetime.fromisoformat(tf_j["semanticSegments"][idx]["startTime"]) < d_exif:
            
            cur_obj = tf_j["semanticSegments"][idx]

            if "visit" in cur_obj:
                vi_idx = idx
            elif "activity" in cur_obj:
                act_idx = idx
            elif "timelinePath" in cur_obj:
                tp_idx = idx

            idx += 1

        #
        # check if each segment actually contains the picture time (i.e., it does not
        # end beforehand). prioritize timelinePath over visit over activity, based on
        # our experience of its accuracy
        #
        if d_exif < datetime.fromisoformat(tf_j["semanticSegments"][tp_idx]["endTime"]):
            idx = tp_idx
            cur_obj = tf_j["semanticSegments"][tp_idx]
        elif d_exif < datetime.fromisoformat(tf_j["semanticSegments"][vi_idx]["endTime"]):
            idx = vi_idx
            cur_obj = tf_j["semanticSegments"][vi_idx]
        elif d_exif < datetime.fromisoformat(tf_j["semanticSegments"][act_idx]["endTime"]):
            idx = act_idx
            cur_obj = tf_j["semanticSegments"][act_idx]
        else:
            cur_obj = {}
            print(jpg, " :(")
            continue 

        # parse segment by type:
        if "visit" in cur_obj:

            # visits provide us a latlong directly
            latlng = cur_obj["visit"]["topCandidate"]["placeLocation"]["latLng"]
            lat = float(latlng.split(", ")[0][:-2])
            lng = float(latlng.split(", ")[1][:-2])
            lat = float(lat)
            lng = float(lng)

            gps_latititude = lat
            gps_longitude = lng

            print(jpg, ", visit: ", cur_obj["visit"]["topCandidate"]["placeLocation"]["latLng"].replace("Â°", ""))

        elif "activity" in cur_obj:

            #
            # activities provide us a start and end time, and a start and end
            # lat/long. interpolate!
            #
            full_dist = datetime.fromisoformat(cur_obj["endTime"]) - datetime.fromisoformat(cur_obj["startTime"])
            photo_dist = d_exif - datetime.fromisoformat(cur_obj["startTime"])

            #
            # if negative, we will be sad.
            #
            if(abs(photo_dist) != photo_dist):
                raise "uh-oh"
            
            start_latlng = cur_obj["activity"]["start"]["latLng"]
            end_latlng = cur_obj["activity"]["end"]["latLng"]

            start_lat = float(start_latlng.split(", ")[0][:-2])
            start_lng = float(start_latlng.split(", ")[1][:-2])
            end_lat = float(end_latlng.split(", ")[0][:-2])
            end_lng = float(end_latlng.split(", ")[1][:-2])

            interp = photo_dist/full_dist

            interp_lat = interp * end_lat + (1 - interp) * start_lat
            interp_lng = interp * end_lng + (1 - interp) * start_lng

            gps_latititude = interp_lat
            gps_longitude = interp_lng

            interp_str = str(interp_lat) + ", " + str(interp_lng)

            print(jpg, ", activity: ", interp_str)

        elif "timelinePath" in cur_obj:
            idx2 = 0

            #
            # timelinePaths consist of a series of points and time. walk the path until
            # we find the first point in the path after the photo was taken.
            #
            while idx2 < len(cur_obj["timelinePath"]) and datetime.fromisoformat(cur_obj["timelinePath"][idx2]["time"]) < d_exif:
                idx2 += 1

            # if all points are after the photo was taken, use the first point
            if idx2 == 0:
                print(jpg, ", start path, ", cur_obj["timelinePath"][idx2]["point"].replace("Â°", ""))

                latlng = cur_obj["timelinePath"][idx2]["point"]
                lat = float(latlng.split(", ")[0][:-2])
                lng = float(latlng.split(", ")[1][:-2])
                lat = float(lat)
                lng = float(lng)

                gps_latititude = lat
                gps_longitude = lng

            # if all points are before the photo was taken, use the last point
            elif idx2 == len(cur_obj["timelinePath"]):
                print(jpg, ", end path, ", cur_obj["timelinePath"][idx2 - 1]["point"].replace("Â°", ""))

                latlng = cur_obj["timelinePath"][idx2 - 1]["point"]
                lat = float(latlng.split(", ")[0][:-2])
                lng = float(latlng.split(", ")[1][:-2])
                lat = float(lat)
                lng = float(lng)

                gps_latititude = lat
                gps_longitude = lng

            # otherwise, interpolate between the first point after and the last point before
            else:

                start = cur_obj["timelinePath"][idx2 - 1]
                end = cur_obj["timelinePath"][idx2]

                full_dist = datetime.fromisoformat(end["time"]) - datetime.fromisoformat(start["time"])
                photo_dist = d_exif - datetime.fromisoformat(start["time"])

                if(abs(photo_dist) != photo_dist):
                    raise "uh-oh"
                
                start_latlng = start["point"]
                end_latlng = end["point"]

                start_lat = float(start_latlng.split(", ")[0][:-2])
                start_lng = float(start_latlng.split(", ")[1][:-2])
                end_lat = float(end_latlng.split(", ")[0][:-2])
                end_lng = float(end_latlng.split(", ")[1][:-2])

                interp = photo_dist/full_dist

                interp_lat = interp * end_lat + (1 - interp) * start_lat
                interp_lng = interp * end_lng + (1 - interp) * start_lng

                gps_latititude = interp_lat
                gps_longitude = interp_lng
                interp_str = str(interp_lat) + ", " + str(interp_lng)

                print(jpg, ", path: ", interp_str)
        
        outfile = output_path + jpg
        os.makedirs(os.path.dirname(outfile), exist_ok=True)

        # apply a custom override if one is present
        if jpg[jpg.find("DSCF") + 4:-4] in custom_override:
            gps_latititude, gps_longitude = custom_override[jpg[jpg.find("DSCF") + 4:-4]]
            print("overriding " + jpg[jpg.find("DSCF") + 4:-4])

        # call exiftool to output the image
        command = [
            exiftool_path,
            f"-GPSLatitude={gps_latititude}",
            f"-GPSLatitudeRef={'N' if gps_latititude >= 0 else 'S'}",
            f"-GPSLongitude={gps_longitude}",
            f"-GPSLongitudeRef={'E' if gps_longitude >= 0 else 'W'}",
            f"-o",
            os.path.dirname(outfile),
            jpg
        ]

        subprocess.run(command, stdout=subprocess.DEVNULL)

    else:
        print(jpg, 'no date')