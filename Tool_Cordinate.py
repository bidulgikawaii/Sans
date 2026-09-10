def world_to_screen(world_x, world_y, camera_x, camera_y, zoom=1.0):
    return (world_x - camera_x) * zoom, (world_y - camera_y) * zoom


def screen_to_world(screen_x, screen_y, camera_x, camera_y, zoom=1.0):
    return screen_x / zoom + camera_x, screen_y / zoom + camera_y


def get_object_world_center(obj_x, obj_y, obj_width, obj_height):
    return obj_x + (obj_width // 2), obj_y + (obj_height // 2)


def get_object_screen_center(obj_x, obj_y, obj_width, obj_height, camera_x, camera_y, zoom=1.0):
    screen_x, screen_y = world_to_screen(obj_x, obj_y, camera_x, camera_y, zoom)
    return screen_x + (obj_width * zoom / 2), screen_y + (obj_height * zoom / 2)


def get_player_world_center(player_x, player_y, player_width, player_height):
    return get_object_world_center(player_x, player_y, player_width, player_height)


def get_player_screen_center(player_x, player_y, player_width, player_height, camera_x, camera_y, zoom=1.0):
    return get_object_screen_center(player_x, player_y, player_width, player_height, camera_x, camera_y, zoom)


def get_camera_target(player_world_center_x, player_world_center_y, screen_width, screen_height, zoom=1.0):
    return player_world_center_x - screen_width / (2 * zoom), player_world_center_y - screen_height / (2 * zoom)
