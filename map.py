import folium
import json
from folium import plugins

with open('land.geojson') as f:
    worldArea = json.load(f)

#for some reason you need to add an attr to make the 'None' tiles work
worldMap = folium.Map(
    location=[0, 0],
    tiles='None',
    attr="<a href=https://michaelweinberg.org/> </a>",
    zoom_start=2,)

#this styles the geojson layer
layer_style = {'fillColor': '#FFFAFA', 'color': 'black'}
folium.GeoJson(
    worldArea,
    style_function=lambda
    x:layer_style).add_to(worldMap)

#this adds and styles the marker
folium.CircleMarker(
    (34.0522, -118.2437),
    radius=10,
    weight=4,
    color="black",
    fill_color="black",
    fill_opacity=.5).add_to(worldMap)

worldMap.save('worldmap.html')