import requests
import time
import random

lat_lon_matrix = [[40.0, 75.0], [40.0, 74.9871836], [40.0, 74.9743672], [40.2563275, 75.0], [40.2563275, 74.9871836], [40.2563275, 74.9743672], [40.512655, 75.0], [40.512655, 74.9871836], [40.512655, 74.9743672]]

elevation_matrix = []

def create_elevation_matrix(input_lat_lon_matrix):
    for i in input_lat_lon_matrix:
        #get the lat from the entry
        grid_lat = i[0]
        #get the lon from the entry
        grid_lon = i[1]
        #generate the URL for the API
        query_url = "http://localhost:5000/v1/etopo1?locations=" + str(grid_lat) + "," + str(grid_lon)
        #query the API with the URL
        r = requests.get(query_url)
        #get the json from the response
        output_elevation_json = r.json()
        print(output_elevation_json)


        #add the elevation to the elevation matrix
        #elevation_matrix.append(output_elevation_json["results"][0]["elevation"])
        #print just to track the progress
        #print(output_elevation_json["results"][0]["elevation"])
        #pause as per API rules - you don't need this to be 1 any more if you self-host
        time.sleep(.1)

create_elevation_matrix(lat_lon_matrix)
