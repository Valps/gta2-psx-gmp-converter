from pathlib import Path
import shutil
import argparse
import sys
import os

PROGRAM_NAME = os.path.basename(sys.argv[0])
ROOT_DIR = Path(__file__).parent

MAP_WIDTH = 255
MAP_HEIGHT = 255

MAP_MAX_Z = 7

BLOCK_INFO_SIZE = 12
LIGHT_INFO_SIZE = 16
ZONE_TYPE_COORDS_DATA_SIZE = 5     # not includes the name length neither the name itself

LIGHT_MAX_X = 32767     # 255*128 + 64 - 1, where 64 = max offset
LIGHT_MAX_Y = 32767     # 255*128 + 64 - 1

CMAP_DATA_SIZE = 256*256*2
BLOCK_INFO_PAD_SIZE = int("0x600", 16)

FIRST_CMAP_PADDING_SIZE = int("0x400", 16)
SECOND_CMAP_PADDING_SIZE = int("0x600", 16)

CHUNK_PADDING_BYTE = int("0xAA", 16)

UMAP_SIZE = BLOCK_INFO_SIZE*256*256*8

def get_filename(path):
    str_path = str(path)
    i = str_path.rfind('\\') + 1
    j = str_path.rfind('.')
    return str_path[i:j]

def convert_int_to_dword(integer):  # low endian
    """Convert a integer to a four byte array in little endian."""
    b1 = integer % 256
    b2 = (integer >> 8) % 256
    b3 = (integer >> 16) % 256
    b4 = (integer >> 24) % 256
    return bytes([b1, b2, b3, b4])

def convert_int_to_word(integer):  # low endian
    """Convert a integer to a two byte array in little endian."""
    b1 = integer % 256
    b2 = integer // 256
    return bytes([b1, b2])

def read_block_side_info(side, str_side):
    tile_texture_idx = (side % 1024)
    side = side >> 10

    wall = (side % 2)
    side = side >> 1

    bullet_wall = (side % 2)
    side = side >> 1

    flat = (side % 2)
    side = side >> 1

    flip = (side % 2)
    side = side >> 1

    tile_rotation = side

    print(f"{str_side} tile: {tile_texture_idx}")
    #print(f"Tile rotation: {return_rotation_value_str(tile_rotation)}°")
    #print(f"Wall: {wall}, Bullet Wall: {bullet_wall}")
    #print(f"Flat: {flat}")
    #print(f"Flip: {flip}")

def read_lid_info(lid):
    tile_texture_idx = (lid % 1024)
    lid = lid >> 10

    lighting_filter = (lid % 4)
    lid = lid >> 2

    flat = (lid % 2)
    lid = lid >> 1

    flip = (lid % 2)
    lid = lid >> 1

    tile_rotation = lid

    print(f"Lid tile: {tile_texture_idx}")
    #print(f"Tile rotation: {tile_rotation}°")
    #print(f"Filter: {lighting_filter}")
    #print(f"Flat: {flat}")
    #print(f"Flip: {flip}")

def is_slope(block_data):
    slope_byte = block_data[-1]
    slope_byte = slope_byte >> 2
    if (slope_byte == 0):
        return False
    if (slope_byte > 60):
        return False
    return True

def print_all_info_block_data(block_data):
    left_side = int.from_bytes(block_data[0:2], 'little')
    right_side = int.from_bytes(block_data[2:4], 'little')
    top_side = int.from_bytes(block_data[4:6], 'little')
    bottom_side = int.from_bytes(block_data[6:8], 'little')
    lid = int.from_bytes(block_data[8:10], 'little')

    #print("Left side info:")
    read_block_side_info(left_side, "Left")

    #print("\nRight side info:")
    read_block_side_info(right_side, "Right")

    #print("\nTop side info:")
    read_block_side_info(top_side, "Top")

    #print("\nBottom side info:")
    read_block_side_info(bottom_side, "Bottom")

    #print("\nLid info:")
    read_lid_info(lid)

def fix_psx_slope(block_data):
    slope_byte = block_data[-1]
    slope_type = slope_byte >> 2
    if (49 <= slope_type <= 52):
        lid = int.from_bytes(block_data[8:10], 'little')
        tile_texture_idx = (lid % 1024)
        if tile_texture_idx == 384:
            tile_texture_idx = 1023
            lid = lid | tile_texture_idx    # set all lowest 10 bits to 1  (1111 1111 11 = 1023)
            new_block_data = block_data[:8] + bytes([lid % 256, lid // 256]) + block_data[10:]
        else:
            new_block_data = block_data     # do nothing
    else:
        new_block_data = block_data     # do nothing
    return new_block_data

def read_psx_map(gmp_path):

    psx_chunk_info = dict(CMAP = [None, None], 
                   ZONE = [None, None], 
                   ANIM = [None, None],
                   RGEN = [None, None])

    cmap_info =  dict(column_start = None, 
                   block_info_1_start = None, 
                   block_info_2_start = None,
                   column_words = None,
                   num_complete_blocks = None,
                   num_lid_blocks_only = None)
    
    with open(gmp_path, 'rb') as file:

        data_offset = file.tell()
        size = file.seek(0, os.SEEK_END)
        file.seek(data_offset)

        print("File Size: {:,} bytes".format(size))

        current_offset = data_offset

        while (current_offset < size):
            chunk_header = file.read(4).decode('ascii')
            current_offset += 4
            if (chunk_header == "CMAP" 
                or chunk_header == "ZONE"
                or chunk_header == "ANIM"
                or chunk_header == "RGEN"
                ):
                header_data_offset = file.tell() + 4
                psx_chunk_info[chunk_header][0] = header_data_offset

                print(f"Header {chunk_header} found! Offset: {hex(header_data_offset)}", end = '')

                if chunk_header == "CMAP":
                    file.read(4)    # read fake header size
                    file.read(CMAP_DATA_SIZE)   # skip data
                    column_words = int.from_bytes(file.read(2), 'little')

                    cmap_info["column_words"] = column_words
                    cmap_info["column_start"] = file.tell()

                    # skip column data and the first padding: go to first block info section
                    file.read(2*column_words + FIRST_CMAP_PADDING_SIZE)

                    cmap_info["block_info_1_start"] = file.tell()

                    num_complete_blocks = int.from_bytes(file.read(2), 'little')    # number of blocks with non-null sides
                    cmap_info["num_complete_blocks"] = num_complete_blocks

                    # skip first block info data section
                    file.read(num_complete_blocks*BLOCK_INFO_SIZE + SECOND_CMAP_PADDING_SIZE)

                    cmap_info["block_info_2_start"] = file.tell()

                    num_lid_blocks_only = int.from_bytes(file.read(2), 'little')    # number of blocks with only lid, arrow & slope data

                    cmap_info["num_lid_blocks_only"] = num_lid_blocks_only

                    # skip second block info data section
                    file.read(num_lid_blocks_only*4)

                    #print(f"Tell: {hex(file.tell())}")

                    num_terminators = 0

                    terminator = int.from_bytes(file.read(1))
                    if terminator == CHUNK_PADDING_BYTE:
                        while terminator == CHUNK_PADDING_BYTE:
                            num_terminators += 1
                            end_offset = file.tell()
                            terminator = int.from_bytes(file.read(1))
                    else:
                        print("ERROR: Wrong CMAP size")
                        sys.exit(-1)
                    
                    file.seek(end_offset)   # get back to finish
                    chunk_size = end_offset - header_data_offset

                    psx_chunk_info["CMAP"][1] = chunk_size - num_terminators
                    print(f", Size: {hex(chunk_size)}")

                else:   # chunk_header == "ZONE" or chunk_header == "ANIM" or chunk_header == "RGEN"
                    data_size = int.from_bytes(file.read(4),'little')
                    file.read(data_size)

                    num_terminators = 0
                    
                    if chunk_header != "RGEN":
                        terminator = int.from_bytes(file.read(1))
                        if terminator == CHUNK_PADDING_BYTE:
                            while terminator == CHUNK_PADDING_BYTE:
                                num_terminators += 1
                                end_offset = file.tell()
                                terminator = int.from_bytes(file.read(1))
                        else:
                            print("ERROR: Wrong chunk size")
                            sys.exit(-1)

                        file.seek(end_offset)   # get back to chunk finish offset
                    else:
                        end_offset = file.tell() + 2
                        current_offset += 2

                    
                    
                    chunk_size = end_offset - header_data_offset

                    psx_chunk_info[chunk_header][1] = chunk_size - num_terminators
                    print(f", Size: {hex(chunk_size)}")

                current_offset += chunk_size + 4 + num_terminators
    print("")
    return ( psx_chunk_info, cmap_info )

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

############ CMAP stuff

def CMAP_read_all_columns(gmp_path, chunk_infos):
    
    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["CMAP"][0]
        size = chunk_infos["CMAP"][1]

        file.seek(dmap_offset + CMAP_DATA_SIZE)
        column_words = int.from_bytes(file.read(2), 'little')

        print(f"Num of columns words: {column_words}")

        words = 0
        column_idx = 0

        while (words < column_words):
            start_offset = file.tell()

            column_height = int.from_bytes(file.read(1))
            column_offset = int.from_bytes(file.read(1))
            num_blocks = column_height - column_offset
            
            if column_height > 7:
                print(f"\nError: height {column_height} above 7. Column {column_idx} at offset {hex(start_offset)}")
                print(f"words count = {words}")
                sys.exit(-1)

            if column_offset > 7:
                print(f"\nError: BlockOffset {column_offset} above 7. Column {column_idx} at offset {hex(start_offset)}")
                print(f"words count = {words}")
                sys.exit(-1)

            # get back to start position
            file.seek(start_offset)

            # 1 for height, 1 for offset, 2*num_blocks for blockd
            column_size = 1 + 1 + 2*num_blocks

            if column_size < 0:
                print(f"ERROR: negative column_size: {column_size}")
                print(f"Column: {column_idx}, Height = {column_height}, Block Offset = {column_offset}")
                print(f"File Offset: {hex(start_offset)}")
                sys.exit(-1)

            file.read(column_size)

            words += column_size // 2
            column_idx += 1
        
        print(f"Number of columns: {column_idx}")

        column_finish_offset = file.tell()
        print(f"Column data start offset: {hex(dmap_offset + CMAP_DATA_SIZE + 2)}")
        print(f"Column data finish offset: {hex(column_finish_offset)}")

        block_data_info_offset = column_finish_offset + 1024 # TODO: psx vs pc CMAP: include 1024 (padding?)
        

        file.seek(block_data_info_offset)  
        num_total_blocks = int.from_bytes(file.read(2), 'little')
        print(f"Num unique blocks: {num_total_blocks}")

        block_data_finish_offset = block_data_info_offset + num_total_blocks*BLOCK_INFO_SIZE


    print(f"Block info start offset = {hex(block_data_info_offset)}")
    print(f"Block info end offset = {hex(block_data_finish_offset)}")

    return block_data_info_offset + 2, block_data_finish_offset, num_total_blocks

def PSX_CMAP_decompress(gmp_path, chunk_infos, cmap_info):
    strange_blocks = 0
    normal_blocks = 0
    max_idx_below_8000 = 0
    max_idx_above_8000 = 0
    min_idx_above_8000 = 40000
    # initialize block info array with empty blocks
    empty_block_data = bytes([0 for _ in range(BLOCK_INFO_SIZE)])
    block_info_array = [ [ [empty_block_data for _ in range(MAP_WIDTH+1)] for _ in range(MAP_HEIGHT+1) ] for _ in range(MAP_MAX_Z+1) ]

    with open(gmp_path, 'rb') as file:
        
        cmap_offset = chunk_infos["CMAP"][0]
        size = chunk_infos["CMAP"][1]

        # block info data starts at
        block_info_array_offset = cmap_info["block_info_1_start"] + 2   #block_data_info_offset

        #print(f"Unknown data again: {hex(block_data_finish_offset + 1536 + 4)}")

        for y in range(MAP_HEIGHT+1):
            for x in range(MAP_WIDTH+1):
                tgt_block_column_data_offset = cmap_offset + 2*(x + y*256)

                file.seek(tgt_block_column_data_offset)

                words_offset = int.from_bytes(file.read(2), 'little')
                tgt_column_offset = cmap_offset + CMAP_DATA_SIZE + 2 + 2*words_offset

                file.seek(tgt_column_offset)

                column_height = int.from_bytes(file.read(1))
                column_offset = int.from_bytes(file.read(1))
                num_blocks = column_height - column_offset

                #if x == 20 and y == 75:
                #    print(f"({x}, {y}) Column offset: {hex(tgt_column_offset)}")

                all_column_blocks_id = []

                # get all block ids from this column
                for block_idx in range(num_blocks):
                    block_id = int.from_bytes( file.read(2), 'little' )

                    # TODO: testing
                    if block_id >= 32768:
                        strange_blocks += 1
                        if block_id > max_idx_above_8000:
                            max_idx_above_8000 = block_id
                        if block_id < min_idx_above_8000:
                            min_idx_above_8000 = block_id
                    else:
                        normal_blocks += 1
                        if block_id > max_idx_below_8000:
                            max_idx_below_8000 = block_id

                    all_column_blocks_id.append( block_id )

                # get block info from each block using its id
                for blockd_idx, block_id in enumerate(all_column_blocks_id):
                    if (block_id < 32768):
                        block_info_offset = block_info_array_offset + BLOCK_INFO_SIZE*block_id  #block_id*BLOCK_INFO_SIZE
                        file.seek( block_info_offset )
                        block_data = file.read(BLOCK_INFO_SIZE)

                        # now fix tile 384 to 1023 for 3-sided slopes
                        if is_slope(block_data):
                            block_data = fix_psx_slope(block_data)
                    else:
                        block_info_offset = cmap_info["block_info_2_start"] + 2 + 4*(block_id - 32768)
                        file.seek( block_info_offset )
                        lid_slope_data = file.read(4)
                        block_data = bytes([0,0  ,  0,0  ,  0,0  ,  0,0 ]) + lid_slope_data
                    
                    z = column_offset + blockd_idx
                    block_info_array[z][y][x] = block_data

    return block_info_array

def get_gmp_zones(psx_gmp_path, chunk_infos):
    zones_data_array = []
    with open(psx_gmp_path, 'rb') as file:

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

def get_gmp_anims(psx_gmp_path, chunk_infos):

    with open(psx_gmp_path, 'rb') as file:

        anim_offset = chunk_infos["ANIM"][0]
        size = chunk_infos["ANIM"][1]

        file.seek(anim_offset)

        all_anim_data = file.read(size)

    return all_anim_data


def create_gmp(output_path, block_info_array, zones_info_array, all_anim_data, chunk_info, edit_file):
    with open(output_path, 'w+b') as file:
        signature = str.encode("GBMP")
        file.write(signature)

        version = convert_int_to_word(500)
        file.write(version)

        # UMAP
        chunk_header = str.encode("UMAP")
        file.write(chunk_header)

        umap_size = convert_int_to_dword(UMAP_SIZE)
        file.write(umap_size)

        for z in range(len(block_info_array)):
            for y in range(len(block_info_array[z])):
                for x in range(len(block_info_array[z][y])):
                    file.write(block_info_array[z][y][x])

        # ZONE
        chunk_header = str.encode("ZONE")
        file.write(chunk_header)

        zone_size = convert_int_to_dword(chunk_info["ZONE"][1])
        file.write(zone_size)

        for zone in zones_info_array:
            file.write(zone)

        # ANIM
        chunk_header = str.encode("ANIM")
        file.write(chunk_header)

        anim_size = convert_int_to_dword(chunk_info["ANIM"][1])
        file.write(anim_size)

        file.write(all_anim_data)

        # EDIT
        if edit_file is not None:
            edit_file_path = ROOT_DIR / edit_file
            if edit_file_path.exists():
                with open(edit_file_path, 'rb') as edit_file:
                    edit_data = edit_file.read()
                    file.write(edit_data)
            else:
                print(f"Warning: {edit_file_path} don't exist!")
        
        
    return

def main():
    parser = argparse.ArgumentParser(PROGRAM_NAME)
    parser.add_argument("psx_gmp_path")
    parser.add_argument("output_gmp_filename")
    parser.add_argument("edit_file", nargs='?')
    args = parser.parse_args()

    if (not args.psx_gmp_path or not args.output_gmp_filename):
        print("Usage: python [program path] [psx gmp path] [output gmp filename]")
        sys.exit(-1)

    # get input gmp path
    if ("\\" not in args.psx_gmp_path and "/" not in args.psx_gmp_path):
        psx_gmp_path = ROOT_DIR / args.psx_gmp_path
    else:
        psx_gmp_path = Path(args.psx_gmp_path)

    # verify if the input gmp map exists
    if (not psx_gmp_path.exists()):
        print(f"Input gmp file doesn't exists. Path: {psx_gmp_path}")
        sys.exit(-1)
    
    print(f"\nOpening file {psx_gmp_path}...\n")
    chunk_infos, cmap_info = read_psx_map(psx_gmp_path)

    print("Column start offset: {}".format(hex(cmap_info["column_start"])))
    print("Complete block info start offset: {}".format(hex(cmap_info["block_info_1_start"])))
    print("Lid only block info start offset: {}".format(hex(cmap_info["block_info_2_start"])))
    print("Num of unique complete blocks: {}".format(cmap_info["num_complete_blocks"]))
    print("Num of unique lid only blocks: {}".format(cmap_info["num_lid_blocks_only"]))

    #return

    block_info_array = PSX_CMAP_decompress(psx_gmp_path, chunk_infos, cmap_info)
    zones_info_array = get_gmp_zones(psx_gmp_path, chunk_infos)
    all_anim_data = get_gmp_anims(psx_gmp_path, chunk_infos)
    
    #write_uncompressed_map(output_path, tgt_chunk_infos, block_info_array)

    if args.edit_file:
        edit_file = args.edit_file
    else:
        edit_file = None

    # now create the gmp file
    output_path = ROOT_DIR / args.output_gmp_filename

    print(f"Creating gmp file at {output_path}...")
    create_gmp(output_path, block_info_array, zones_info_array, all_anim_data, chunk_infos, edit_file)
    print("Success!")
        


if __name__ == "__main__":
    main()