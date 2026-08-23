import requests
import time
import random


######## Setup Section #############
#let's start with a 5x5 grid
grid_x = 3
grid_y = 3

#make this easy by defining the upper left point, not the center
#start_lat = 40.765201
#start_lon = -74.092170
start_lat = 40
start_lon = 75

#these are for the pixels in any given frame
lat_increment = 0.2563275
lon_increment = 0.0128164

#these are for shifting the entire frame
lat_frame_shift_increment = 1
lon_frame_shift_increment = 1

#these are to slightly randomize the frame shift when it bounces
#this avoids just running the same path over and over
frame_shift_random_lower_bound = -0.2
frame_shift_random_upper_bound = 0.2


######### Create the lat_lon matrix ##########

lat_lon_matrix = []

#
def create_lat_lon_matrix(input_lat, input_lon, input_lat_increment, input_lon_increment, input_grid_x, input_grid_y):
    #the order of the loops matters here
    for x in range(input_grid_x):
        for y in range(input_grid_y):
            point_lat = input_lat + (x * input_lat_increment)
            #this is minus because the anchor point is in the upper left
            point_lon = input_lon - (y * input_lon_increment)
            lat_lon_matrix.append([point_lat, point_lon])

#create_lat_lon_matrix(start_lat, start_lon, lat_increment, lon_increment, grid_x, grid_y)

#print(lat_lon_matrix)

######### Create the elevation matrix #########

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
        #add the elevation to the elevation matrix
        elevation_matrix.append(output_elevation_json["results"][0]["elevation"])
        #print just to track the progress
        print(output_elevation_json["results"][0]["elevation"])
        #pause as per API rules - you don't need this to be 1 any more if you self-host
        time.sleep(.1)

#create_elevation_matrix(lat_lon_matrix)

#print(elevation_matrix)




#TODO: create color grid
#TODO: convert elevation grid into color grid

elevation_color_matrix = []

def create_elevation_color_matrix(input_elevation_matrix):
    # create the arduion map() function because apparently there isn't one in python?
    def remap_values(x, in_min, in_max, out_min, out_max):
        return int((x-in_min) * (out_max-out_min) / (in_max-in_min) + out_min)
    list_min_value = min(input_elevation_matrix)
    list_max_value = max(input_elevation_matrix)
    list_mid_value = sum(input_elevation_matrix)/len(input_elevation_matrix)
    print("list mid value = " + str(list_mid_value))
    #get the range of elevations in the lat_lon_matrix (highest + lowest)
    #for i in matrix:
        #remap_values(i, matrix_min, matrix_max, 0, 255)

    for i in input_elevation_matrix:
        # i will just be the elevation

        # if elevation is below sea level
        if i <=0:
            #only change the B value
            elevation_color_matrix.append([0, 0, remap_values(i, list_min_value, list_max_value, 0, 255)])
            print("underwater")
        # if the elevation is above sea level
        else:
            #the goal here is to start increasing the R value and then spill over to the G value
            #if i is less than half of the maximum height
            if i <= list_mid_value:
                #only increase the R value
                elevation_color_matrix.append([remap_values(i, list_min_value, list_max_value, 0, 255), 0, 0])
                print("above water and less than half of max grid height")
            else:
                #max out R and increase G value
                # the G value maps the amount of i above the mid point to between zero and the difference between the max_value and the mid_value, which is the number space that I am reserving for G
                elevation_color_matrix.append([255, remap_values((i-list_mid_value), 0, (list_max_value - list_mid_value), 0, 255), 0])
                print("above water and more than half of max grid height")



#TODO: shift grid over time

while True:
    #this is for debugging so you can find the frame
    print("starting point: " + str(start_lat) + " , " + str(start_lon))

    create_lat_lon_matrix(start_lat, start_lon, lat_increment, lon_increment, grid_x, grid_y)

    create_elevation_matrix(lat_lon_matrix)
    print(elevation_matrix)

    #push colors
    create_elevation_color_matrix(elevation_matrix)
    print(elevation_color_matrix)

    #shift the frame
    start_lat = start_lat + lat_frame_shift_increment
    start_lon = start_lon + lon_frame_shift_increment

    #frame bounce with a bit of randomization to keep things interesting
    if (start_lat >= 89 or start_lat <= -89):
        lat_frame_shift_increment = (lat_frame_shift_increment + random.uniform(frame_shift_random_lower_bound, frame_shift_random_upper_bound)) * -1
    if (start_lon >= 179 or start_lon < -179):
        lon_frame_shift_increment = (lon_frame_shift_increment + random.uniform(frame_shift_random_lower_bound, frame_shift_random_upper_bound)) * -1



    #reset the lists to clear out the old data
    lat_lon_matrix = []
    elevation_matrix = []
    elevation_color_matrix = []

    time.sleep(20)

#TODO: add way to arbitrarily change the starting point
