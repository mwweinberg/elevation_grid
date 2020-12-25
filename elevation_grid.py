import requests
import time


######## Setup Section #############
#make this easy by defining the upper left point, not the center
start_lat = 40.765201
start_lon = -74.092170



lat_increment = 0.2563275
lon_increment = 0.0128164



#let's start with a 5x5 grid
grid_x = 5
grid_y = 5

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

create_lat_lon_matrix(start_lat, start_lon, lat_increment, lon_increment, grid_x, grid_y)

print(lat_lon_matrix)

######### Create the elevation matrix #########

elevation_matrix = []


def create_elevation_matrix(input_lat_lon_matrix):
    for i in input_lat_lon_matrix:
        #get the lat from the entry
        grid_lat = i[0]
        #get the lon from the entry
        grid_lon = i[1]
        #generate the URL for the API
        query_url = "https://api.opentopodata.org/v1/test-dataset?locations=" + str(grid_lat) + "," + str(grid_lon)
        #query the API with the URL
        r = requests.get(query_url)
        #get the json from the response
        output_elevation_json = r.json()
        #add the elevation to the elevation matrix
        elevation_matrix.append(output_elevation_json["results"][0]["elevation"])
        #print just to track the progress
        print(output_elevation_json["results"][0]["elevation"])
        #pause as per API rules 
        time.sleep(1)

create_elevation_matrix(lat_lon_matrix)

print(elevation_matrix)




#TODO: create color grid

#TODO: convert elevation grid into color grid

#TODO: shift grid over time

#TODO: add bouncing to the shift so that it stays on earth

#TODO: add way to arbitrarily change the starting point

