grid_matrix = []

#make this easy by defining the upper left point, not the center
#start_lat = 40.765201
#start_lon = -74.092170
start_lat = 1
start_lon = 1

#lat_increment = 0.2563275
#lon_increment = 0.0128164
lat_increment = 1
lon_increment = 1

#let's start with a 5x5 grid
grid_x = 5
grid_y = 5

grid_size = grid_x * grid_y

print(grid_size)

grid_matrix = []

#the order of the loops matters here
for x in range(grid_x):
    for y in range(grid_y):
        point_lat = start_lat + (x * lat_increment)
        point_lon = start_lon + (y * lon_increment)
        grid_matrix.append([point_lat, point_lon])

print(grid_matrix)

#TODO: create elevation grid

#TODO: submit coordinates to api to get elevation, add to grid

#TODO: create color grid

#TODO: convert elevation grid into color grid 

