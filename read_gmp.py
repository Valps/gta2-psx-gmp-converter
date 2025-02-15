from pathlib import Path
import shutil
import argparse
import sys
import os

PROGRAM_NAME = os.path.basename(sys.argv[0])
ROOT_DIR = Path(__file__).parent

PLATFORMS = ["pc", "psx"]

MAP_WIDTH = 255
MAP_HEIGHT = 255

BLOCK_INFO_SIZE = 12
LIGHT_INFO_SIZE = 16
ZONE_TYPE_COORDS_DATA_SIZE = 5     # not includes the name length neither the name itself

LIGHT_MAX_X = 32767     # 255*128 + 64 - 1, where 64 = max offset
LIGHT_MAX_Y = 32767     # 255*128 + 64 - 1

AIR_TYPE = 0
ROAD_TYPE = 1
PAVEMENT_TYPE = 2
FIELD_TYPE = 3

DMAP_COLUMN_OFFSET = 256*256*4
CMAP_COLUMN_OFFSET = 256*256*2

def two_nibble_from_byte(byte):
    upper_nibble = byte // 16
    lower_nibble = byte % 16
    return (upper_nibble, lower_nibble)

def return_rotation_value_str(binary_rotation_type):
    if (binary_rotation_type == 0):
        return "0"
    elif (binary_rotation_type == 1):
        return "90"
    elif (binary_rotation_type == 2):
        return "180"
    elif (binary_rotation_type == 3):
        return "270"
    else:
        print(f"Error: wrong binary rotation type: {binary_rotation_type}")
        sys.exit(-1)

def return_block_type_str(binary_block_type):
    if (binary_block_type == AIR_TYPE):
        return "air"
    elif (binary_block_type == ROAD_TYPE):
        return "road"
    elif (binary_block_type == PAVEMENT_TYPE):
        return "pavement"
    elif (binary_block_type == FIELD_TYPE):
        return "field"
    else:
        print(f"Error: wrong binary block type: {binary_block_type}")
        sys.exit(-1)

def detect_headers_and_get_chunks(gmp_path, psx: bool):

    chunk_info = dict(UMAP = [None, None], 
                   CMAP = [None, None], 
                   DMAP = [None, None], 
                   ZONE = [None, None], 
                   MOBJ = [None, None], 
                   PSXM = [None, None], 
                   ANIM = [None, None],
                   LGHT = [None, None],
                   EDIT = [None, None],
                   THSR = [None, None],
                   RGEN = [None, None])
    

    with open(gmp_path, 'rb') as file:
        
        if not psx:
            signature = file.read(4).decode('ascii')
            if (signature != "GBMP"):
                print("Error!\n")
                print(f"{gmp_path} is not a gmp file!")
                sys.exit(-1)

            version_code = int.from_bytes(file.read(2),'little')

            print(f"File Header: {signature}")
            print(f"Version Code: {version_code}", end="\n\n")

        data_offset = file.tell()
        size = file.seek(0, os.SEEK_END)
        file.seek(data_offset)

        print("File Size: {:,} bytes".format(size))

        current_offset = data_offset

        while (current_offset < size):
            chunk_header = file.read(4).decode('ascii')
            current_offset += 4
            if (chunk_header == "UMAP" 
                or chunk_header == "CMAP"
                or chunk_header == "DMAP"
                or chunk_header == "ZONE"
                or chunk_header == "MOBJ"
                or chunk_header == "PSXM"
                or chunk_header == "ANIM"
                or chunk_header == "LGHT"
                or chunk_header == "EDIT"
                or chunk_header == "THSR"
                or chunk_header == "RGEN"
                ):
                header_data_offset = file.tell() + 4
                chunk_info[chunk_header][0] = header_data_offset

                header_size = int.from_bytes(file.read(4),'little')
                chunk_info[chunk_header][1] = header_size

                print(f"Header {chunk_header} found! Offset: {hex(header_data_offset)}, Size: {hex(header_size)}")

                file.read(header_size)  # skip data

                if psx:
                    # skip AA AA terminators
                    if chunk_header == "CMAP" or chunk_header == "ANIM":
                        file.read(4)
                        current_offset += 4
                    else:
                        file.read(2)
                        current_offset += 2
                
                current_offset += header_size
    print("")
    return chunk_info

def convert_fix16(f_var, get_offset: bool):
    if (get_offset):
        int_part = f_var // 128
        offset = f_var - int_part*128
        return (int_part, offset)
    else:
        return f_var / 128

def read_lid_info(lid):
    data = []

    tile_texture_idx = (lid % 1024)
    data.append(tile_texture_idx)
    lid = lid >> 10

    lighting_filter = (lid % 4)
    data.append(lighting_filter)
    lid = lid >> 2

    flat = (lid % 2)
    data.append(flat)
    lid = lid >> 1

    flip = (lid % 2)
    data.append(flip)
    lid = lid >> 1

    tile_rotation = lid
    data.append(tile_rotation)

    print(f"Lid tile: {tile_texture_idx}")
    print(f"Tile rotation: {return_rotation_value_str(tile_rotation)}°")
    print(f"Filter: {lighting_filter}")
    print(f"Flat: {flat}")
    print(f"Flip: {flip}")
    return data

def read_block_side_info(side):
    data = []

    tile_texture_idx = (lid % 1024)
    data.append(tile_texture_idx)
    lid = lid >> 10

    wall = (lid % 2)
    data.append(wall)
    lid = lid >> 1

    bullet_wall = (lid % 2)
    data.append(bullet_wall)
    lid = lid >> 1

    flat = (lid % 2)
    data.append(flat)
    lid = lid >> 1

    flip = (lid % 2)
    data.append(flip)
    lid = lid >> 1

    tile_rotation = lid
    data.append(tile_rotation)

    print(f"Lid tile: {tile_texture_idx}")
    print(f"Tile rotation: {return_rotation_value_str(tile_rotation)}°")
    print(f"Wall: {wall}, Bullet Wall: {bullet_wall}")
    print(f"Flat: {flat}")
    print(f"Flip: {flip}")
    return data

def read_slope_info(slope_byte):
    block_type = (slope_byte % 4)
    slope_byte = slope_byte >> 2

    slope_type = slope_byte

    print(f"Block type: {return_block_type_str(block_type)}")
    print(f"Slope type: {slope_type}\n")
    return

def read_first_blocks_UMAP(gmp_path, chunk_infos, num_blocks, print_last_block_only: bool):
    with open(gmp_path, 'rb') as file:
        
        umap_offset = chunk_infos["UMAP"][0]

        size = BLOCK_INFO_SIZE*num_blocks    # block_info size: 0xC = 12

        file.seek(umap_offset)
        
        current_offset = umap_offset

        x = 0
        y = 0
        z = 0

        block_idx = 0

        while (current_offset < umap_offset + size):
            
            left = int.from_bytes(file.read(2),'little')
            right = int.from_bytes(file.read(2),'little')
            top = int.from_bytes(file.read(2),'little')
            bottom = int.from_bytes(file.read(2),'little')
            lid = int.from_bytes(file.read(2),'little')

            arrows = int.from_bytes(file.read(1),'little')
            slope_type = int.from_bytes(file.read(1),'little')

            current_offset += BLOCK_INFO_SIZE

            if ( ( print_last_block_only and block_idx == (num_blocks - 1) )
                or not print_last_block_only ):
                print(f"-------- Block ({x}, {y}, {z}):")
                read_lid_info(lid)
                read_slope_info(slope_type)

            x += 1
            if (x > 255):
                x = 0
                y += 1
            if (y > 255):
                y = 0
                z += 1

            block_idx += 1

def get_umap_block_idx_from_xyz(x, y, z):
    return x + y*256 + z*256*256

def read_block_UMAP(gmp_path, chunk_infos, tgt_x, tgt_y, tgt_z):
    with open(gmp_path, 'rb') as file:
        
        umap_offset = chunk_infos["UMAP"][0]
        size = chunk_infos["UMAP"][1]

        file.seek(umap_offset)
        
        current_offset = umap_offset

        block_idx = tgt_x + tgt_y*256 + tgt_z*256*256

        file.seek(umap_offset + BLOCK_INFO_SIZE*block_idx)

        left = int.from_bytes(file.read(2),'little')
        right = int.from_bytes(file.read(2),'little')
        top = int.from_bytes(file.read(2),'little')
        bottom = int.from_bytes(file.read(2),'little')
        lid = int.from_bytes(file.read(2),'little')

        arrows = int.from_bytes(file.read(1),'little')
        slope_type = int.from_bytes(file.read(1),'little')

        print(f"-------- Block ({tgt_x}, {tgt_y}, {tgt_z}):")
        read_lid_info(lid)
        read_slope_info(slope_type)

def get_block_info_data(gmp_path, chunk_infos):

    xyz_array = []

    with open(gmp_path, 'rb') as file:
        umap_offset = chunk_infos["UMAP"][0]
        size = chunk_infos["UMAP"][1]
        file.seek(umap_offset)
        current_offset = umap_offset

        x_array = []
        xy_array = []

        x = 0
        y = 0
        z = 0

        while (current_offset < umap_offset + size):

            block_data = file.read(BLOCK_INFO_SIZE)
            x_array.append(block_data)

            current_offset += BLOCK_INFO_SIZE

            x += 1

            if (x > 255):
                x = 0

                xy_array.append(x_array)
                x_array = []

                y += 1
            
            if (y > 255):
                y = 0

                xyz_array.append(xy_array)
                xy_array = []

                z += 1

    return xyz_array

def is_air_block(block_data):
    block_type_byte = block_data[-1]
    type = block_type_byte % 4
    if (type == AIR_TYPE):
        return True
    return False

def is_empty_block(block_data):
    if (is_air_block(block_data)):
        lid_word = int.from_bytes(block_data[8:10], 'little')
        lid_tile = lid_word % 1024
        if (lid_tile == 0):
            left_word = int.from_bytes(block_data[0:2], 'little')
            right_word = int.from_bytes(block_data[2:4], 'little')
            top_word = int.from_bytes(block_data[4:6], 'little')
            bottom_word = int.from_bytes(block_data[6:8], 'little')
            if (left_word == 0 and right_word == 0 and top_word == 0 and bottom_word == 0):
                return True
    return False

def is_road_field_block(block_data):
    block_type_byte = block_data[-1]
    type = block_type_byte % 4
    if (type == ROAD_TYPE or type == FIELD_TYPE):
        return True
    return False

def block_has_lid(block_data):
    lid_word = int.from_bytes(block_data[8:10], 'little')
    lid_tile = lid_word % 1024
    if (lid_tile != 0):
        return True
    return False

def is_slope(block_data):
    slope_byte = block_data[-1]
    slope_byte = slope_byte >> 2
    if (slope_byte == 0):
        return False
    if (slope_byte > 60):   # slopes 61, 62 and 63 are irrelevants for gmp rotation
        return False
    return True

################ other stuff



def write_uncompressed_map(output_path, chunk_infos, block_info_array):
    with open(output_path, 'r+b') as file:
        
        umap_offset = chunk_infos["UMAP"][0]
        size = chunk_infos["UMAP"][1]

        file.seek(umap_offset)
        
        current_offset = umap_offset

        x = 0
        y = 0
        z = 0

        while (current_offset < umap_offset + size):
            file.write(block_info_array[z][y][x])
                
            x += 1

            if (x > 255):
                x = 0
                y += 1
                
            if (y > 255):
                y = 0
                z += 1
                
            if (z >= 8):
                break

    #print(f"Map blocks rotated successfully by {rotation_angle}°")

def get_zones_info_data(gmp_path, chunk_infos):

    if chunk_infos["ZONE"][0] is None:
        return None # no zones

    zones_data_array = []
    with open(gmp_path, 'rb') as file:

        zone_offset = chunk_infos["ZONE"][0]
        size = chunk_infos["ZONE"][1]

        file.seek(zone_offset)
        
        current_offset = zone_offset
        while (current_offset < zone_offset + size):
            zone_info = file.read(ZONE_TYPE_COORDS_DATA_SIZE)

            current_offset += ZONE_TYPE_COORDS_DATA_SIZE

            name_length = int.from_bytes(file.read(1))
            zone_name_data = file.read(name_length)
            current_offset += 1 + name_length

            zone_data = zone_info + int.to_bytes(name_length) + zone_name_data
            zones_data_array.append(zone_data)

    return zones_data_array

def get_light_info_data(gmp_path, chunk_infos):

    if chunk_infos["LGHT"][0] is None:
        return None # no zones

    lights_data = []
    with open(gmp_path, 'rb') as file:

        lght_offset = chunk_infos["LGHT"][0]
        size = chunk_infos["LGHT"][1]

        file.seek(lght_offset)
        
        current_offset = lght_offset
        while (current_offset < lght_offset + size):
            light_data = file.read(LIGHT_INFO_SIZE)
            lights_data.append(light_data)

            current_offset += LIGHT_INFO_SIZE

    return lights_data














PRINT_COLUMN = False






def CMAP_get_all_columns(gmp_path, chunk_infos):
    columns_array = []
    columns_size_array = []
    
    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["CMAP"][0]
        size = chunk_infos["CMAP"][1]

        file.seek(dmap_offset + CMAP_COLUMN_OFFSET)
        column_words = int.from_bytes(file.read(2), 'little')

        print(f"Num of columns: {column_words}")

        for column_idx in range(column_words):
            start_offset = file.tell()

            if PRINT_COLUMN:
                print(f"Column found at offset: {hex(start_offset)}", end='')

            column_height = int.from_bytes(file.read(1))
            column_offset = int.from_bytes(file.read(1))
            num_blocks = column_height - column_offset
            
            if column_height > 7:
                print(f"\nError: height {column_height} above 7. Column {column_idx} at offset {hex(start_offset)}")
                sys.exit(-1)

            if column_offset > 7:
                print(f"\nError: BlockOffset {column_offset} above 7. Column {column_idx} at offset {hex(start_offset)}")
                sys.exit(-1)

            # get back to start position
            file.seek(start_offset)

            # 1 for height, 1 for offset, 2*num_blocks for blockd
            column_size = 1 + 1 + 2*num_blocks
            columns_size_array.append(column_size)

            if PRINT_COLUMN:
                print(f", column size: {column_size}, h = {column_height}, o = {column_offset}")

            if column_size < 0:
                print(f"ERROR: negative column_size: {column_size}")
                print(f"Column: {column_idx}, Height = {column_height}, Block Offset = {column_offset}")
                print(f"File Offset: {hex(start_offset)}")
                sys.exit(-1)

            column_data = file.read(column_size)
            columns_array.append(column_data)

    return ( columns_array , columns_size_array )






















def DMAP_get_all_columns(gmp_path, chunk_infos):
    columns_array = []
    columns_size_array = []
    
    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["DMAP"][0]
        size = chunk_infos["DMAP"][1]

        file.seek(dmap_offset + DMAP_COLUMN_OFFSET)
        column_words = int.from_bytes(file.read(4), 'little')
        #num_unique_blocks = int.from_bytes(file.read(4), 'little')

        #file.read(16*16)

        print(f"Num of columns: {column_words}")
        #print(f"Num of unique blocks: {num_unique_blocks}\n\n")

        for column_idx in range(column_words):
            start_offset = file.tell()

            if PRINT_COLUMN:
                print(f"Column found at offset: {hex(start_offset)}", end='')

            column_height = int.from_bytes(file.read(1))
            column_offset = int.from_bytes(file.read(1))
            num_blocks = column_height - column_offset
            
            if column_height > 7:
                print(f"\nError: height {column_height} above 7. Column {column_idx} at offset {hex(start_offset)}")
                sys.exit(-1)

            if column_offset > 7:
                print(f"\nError: BlockOffset {column_offset} above 7. Column {column_idx} at offset {hex(start_offset)}")
                sys.exit(-1)

            # get back to start position
            file.seek(start_offset)

            # 1 for height, 1 for offset, 2 for pad, 4*num_blocks for blockd
            column_size = 1 + 1 + 2 + 4*num_blocks
            columns_size_array.append(column_size)

            if PRINT_COLUMN:
                print(f", column size: {column_size}, h = {column_height}, o = {column_offset}")

            if column_size < 0:
                print(f"ERROR: negative column_size: {column_size}")
                print(f"Column: {column_idx}, Height = {column_height}, Block Offset = {column_offset}")
                print(f"File Offset: {hex(start_offset)}")
                sys.exit(-1)

            column_data = file.read(column_size)
            columns_array.append(column_data)

    return ( columns_array , columns_size_array )




def DMAP_read_block(gmp_path, chunk_infos, columns_data, columns_size_array, tgt_x, tgt_y, tgt_z):

    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["DMAP"][0]
        size = chunk_infos["DMAP"][1]

        tgt_block_column_data_offset = dmap_offset + 4*(tgt_x + tgt_y*256)

        print(f"Block column idx at offset {hex(tgt_block_column_data_offset)}")

        file.seek(tgt_block_column_data_offset)

        column_index = int.from_bytes(file.read(4), 'little')

        print(f"Target Column index: {column_index}")
        
        tgt_column_data = columns_data[column_index]

        # 0 = height
        # 1 = offset
        # 2,3 = pad
        # ... = blockd

        blocks_num = tgt_column_data[0] - tgt_column_data[1]   # height - offset

        print("\nColumn Data:")
        print(f"Height: {tgt_column_data[0]}")
        print(f"Offset: {tgt_column_data[1]}")
        print(f"Num Blocks: {blocks_num}\n")

        all_column_blocks_id = []

        for block_idx in range(blocks_num):
            block_id = int.from_bytes( tgt_column_data[4 : 4 + 4*(block_idx+1)] ,'little' )
            all_column_blocks_id.append( block_id )

        all_columns_data_size = sum(columns_size_array)

        # now go to block section
        # 4 for column_words dword

        block_info_array_offset = ( dmap_offset 
                  + DMAP_COLUMN_OFFSET 
                  + 4 
                  + all_columns_data_size 
                  + BLOCK_INFO_SIZE*(tgt_z - tgt_column_data[1]) )

        file.seek( block_info_array_offset )

        print(hex(block_info_array_offset))
        
        #dword = int.from_bytes(file.read(4), 'little')

        #print(dword)
        
        

def read_gmp(gmp_path, chunk_infos, psx):

    #if chunk_infos["UMAP"][0] is None:
    #    print("Error: This program only support maps which have UMAP header.")
    #    sys.exit(-1)

    if not psx and chunk_infos["DMAP"][0] is None:
        print("Error: This program only read compressed maps.")
        sys.exit(-1)

    if psx and chunk_infos["CMAP"][0] is None:
        print("Error: This program only read compressed maps.")
        sys.exit(-1)

    # create a copy of gmp file
    #str_gmp_path = str(gmp_path)
    #i = str_gmp_path.rfind('\\') + 1
    #j = str_gmp_path.rfind('.')

    #filename = str_gmp_path[i:j]
    #output_path = ROOT_DIR / f"{filename}_rotated.gmp"

    #print(f"Creating copy of {filename}.gmp")
    #shutil.copyfile(gmp_path, output_path)

    x, y, z = 146, 154, 2
    #x, y, z = 2, 2, 3

    if not psx:
        columns_data, columns_size_array = DMAP_get_all_columns(gmp_path, chunk_infos)
        DMAP_read_block(gmp_path, chunk_infos, columns_data, columns_size_array, x, y, z)
    else:
        columns_data, columns_size_array = CMAP_get_all_columns(gmp_path, chunk_infos)



    # get block infos
    #block_info_array = get_block_info_data(gmp_path, chunk_infos)
    #zones_info_array = get_zones_info_data(gmp_path, chunk_infos)
    #light_info_array = get_light_info_data(gmp_path, chunk_infos)

    



def main():
    parser = argparse.ArgumentParser(PROGRAM_NAME)
    parser.add_argument("gmp_path")
    parser.add_argument("platform")
    args = parser.parse_args()

    if (not args.gmp_path
        or args.platform.lower() not in PLATFORMS):
        print("Usage: python [program path] [gmp path] [platform=pc,psx]")
        sys.exit(-1)

    if ("\\" not in args.gmp_path and "/" not in args.gmp_path):
        gmp_path = ROOT_DIR / args.gmp_path
    else:
        gmp_path = Path(args.gmp_path)

    if (not gmp_path.exists()):
        print("File not found.")
        sys.exit(-1)

    if args.platform.lower() == "psx":
        is_psx = True
    else:
        is_psx = False
    
    chunk_infos = detect_headers_and_get_chunks(gmp_path, is_psx)
    read_gmp(gmp_path, chunk_infos, is_psx)
        


if __name__ == "__main__":
    main()
