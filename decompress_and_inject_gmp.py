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

MAP_MAX_Z = 7

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

def get_filename(path):
    str_path = str(path)
    i = str_path.rfind('\\') + 1
    j = str_path.rfind('.')
    return str_path[i:j]

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
            #print(f"Current offset: {file.tell()}")
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
                    return chunk_info           # TODO: PSX chunk sizes doesn't work at all
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

############ DMAP stuff

def DMAP_read_all_columns(gmp_path, chunk_infos):
    
    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["DMAP"][0]
        size = chunk_infos["DMAP"][1]

        file.seek(dmap_offset + DMAP_COLUMN_OFFSET)
        column_words = int.from_bytes(file.read(4), 'little')

        print(f"Num of columns words: {column_words}")

        words = 0
        column_idx = 0

        while (words < 2*column_words):
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

            # 1 for height, 1 for offset, 2 for pad, 4*num_blocks for blockd
            column_size = 1 + 1 + 2 + 4*num_blocks

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

        print(f"Column data finish offset: {hex(column_finish_offset)}")

        num_total_blocks = int.from_bytes(file.read(4), 'little')
        print(f"Num of unique blocks: {num_total_blocks}")

    return column_finish_offset + 4

def DMAP_uncompress(gmp_path, chunk_infos, column_finish_offset):
    # initialize block info array with empty blocks
    empty_block_data = bytes([0 for _ in range(BLOCK_INFO_SIZE)])
    block_info_array = [ [ [empty_block_data for _ in range(MAP_WIDTH+1)] for _ in range(MAP_HEIGHT+1) ] for _ in range(MAP_MAX_Z+1) ]

    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["DMAP"][0]
        size = chunk_infos["DMAP"][1]

        for y in range(MAP_HEIGHT+1):
            for x in range(MAP_WIDTH+1):
                tgt_block_column_data_offset = dmap_offset + 4*(x + y*256)

                file.seek(tgt_block_column_data_offset)

                words_offset = int.from_bytes(file.read(4), 'little')
                tgt_column_offset = dmap_offset + DMAP_COLUMN_OFFSET + 4 + 4*words_offset

                file.seek(tgt_column_offset)

                column_height = int.from_bytes(file.read(1))
                column_offset = int.from_bytes(file.read(1))
                num_blocks = column_height - column_offset

                #print(f"x,y = ({x}, {y})")
                #print(f"Height: {column_height}")
                #print(f"Offset: {column_offset}\n\n")

                all_column_blocks_id = []

                file.read(2)    # skip padding

                # get all block ids from this column
                for block_idx in range(num_blocks):
                    block_id = int.from_bytes( file.read(4) ,'little' )
                    all_column_blocks_id.append( block_id )

                # block info data starts at
                block_info_array_offset = column_finish_offset

                # get block info from each block using its id
                for blockd_idx, block_id in enumerate(all_column_blocks_id):
                    block_info_offset = block_info_array_offset + block_id*BLOCK_INFO_SIZE
                    file.seek( block_info_offset )
                    block_data = file.read(BLOCK_INFO_SIZE)
                    block_z = column_offset + blockd_idx
                    block_info_array[block_z][y][x] = block_data

    return block_info_array

############ CMAP stuff

def CMAP_read_all_columns(gmp_path, chunk_infos):
    
    with open(gmp_path, 'rb') as file:
        
        dmap_offset = chunk_infos["CMAP"][0]
        size = chunk_infos["CMAP"][1]

        file.seek(dmap_offset + CMAP_COLUMN_OFFSET)
        column_words = int.from_bytes(file.read(2), 'little')

        print(f"Num of columns words: {column_words}")

        words = 0
        column_idx = 0

        while (words < column_words):
            start_offset = file.tell()

            column_height = int.from_bytes(file.read(1))
            column_offset = int.from_bytes(file.read(1))
            num_blocks = column_height - column_offset

            #if column_height == 1 and column_offset == 0:
            #    print(f"Column (h,o) = (1,0) in offset {hex(start_offset)}")
            
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
        print(f"Column data finish offset: {hex(column_finish_offset)}")

        block_data_info_offset = column_finish_offset + 1024 # TODO: psx vs pc CMAP: include 1024 (padding?)

        file.seek(block_data_info_offset)  
        num_total_blocks = int.from_bytes(file.read(2), 'little')
        print(f"Num unique blocks: {num_total_blocks}")


    print(f"Block info start offset = {hex(block_data_info_offset)}")
    print(f"Block info end offset = {hex(block_data_info_offset + num_total_blocks*BLOCK_INFO_SIZE)}")

    return block_data_info_offset + 2

def CMAP_uncompress(gmp_path, chunk_infos, block_data_info_offset):
    max_number = 0
    max_num_offset = 0
    # initialize block info array with empty blocks
    empty_block_data = bytes([0 for _ in range(BLOCK_INFO_SIZE)])
    block_info_array = [ [ [empty_block_data for _ in range(MAP_WIDTH+1)] for _ in range(MAP_HEIGHT+1) ] for _ in range(MAP_MAX_Z+1) ]

    with open(gmp_path, 'rb') as file:
        
        cmap_offset = chunk_infos["CMAP"][0]
        size = chunk_infos["CMAP"][1]

        for y in range(MAP_HEIGHT+1):
            for x in range(MAP_WIDTH+1):
                tgt_block_column_data_offset = cmap_offset + 2*(x + y*256)

                file.seek(tgt_block_column_data_offset)

                words_offset = int.from_bytes(file.read(2), 'little')
                tgt_column_offset = cmap_offset + CMAP_COLUMN_OFFSET + 2 + 2*words_offset

                file.seek(tgt_column_offset)

                column_height = int.from_bytes(file.read(1))
                column_offset = int.from_bytes(file.read(1))
                num_blocks = column_height - column_offset

                #if column_height == 1 and column_offset == 0:
                #    print(f"Column (h,o) = (1,0) in offset {hex(tgt_column_offset)}")

                all_column_blocks_id = []

                # get all block ids from this column
                for block_idx in range(num_blocks):
                    block_id = int.from_bytes( file.read(2), 'little' )
                    if block_id > max_number:
                        max_number = block_id
                        max_num_offset = tgt_column_offset
                    all_column_blocks_id.append( block_id )

                # block info data starts at
                block_info_array_offset = block_data_info_offset

                # get block info from each block using its id
                for blockd_idx, block_id in enumerate(all_column_blocks_id):
                    block_info_offset = block_info_array_offset + 2*block_id  #block_id*BLOCK_INFO_SIZE
                    file.seek( block_info_offset )
                    block_data = file.read(BLOCK_INFO_SIZE)
                    z = column_offset + blockd_idx
                    block_info_array[z][y][x] = block_data
    print(f"Max block ID: {max_number} at column offset {hex(max_num_offset)}")
    return block_info_array




def uncompress_gmp(gmp_path, chunk_infos, psx):

    if not psx and chunk_infos["DMAP"][0] is None:
        print("Error: This program only read compressed maps.")
        sys.exit(-1)

    if psx and chunk_infos["CMAP"][0] is None:
        print("Error: This program only read compressed maps.")
        sys.exit(-1)

    if not psx:
        column_finish_offset = DMAP_read_all_columns(gmp_path, chunk_infos)
        print(f"Column finish offset = {hex(column_finish_offset)}")
        block_info_array = DMAP_uncompress(gmp_path, chunk_infos, column_finish_offset)
    else:
        block_data_info_offset = CMAP_read_all_columns(gmp_path, chunk_infos)
        block_info_array = CMAP_uncompress(gmp_path, chunk_infos, block_data_info_offset)

    return block_info_array


def main():
    parser = argparse.ArgumentParser(PROGRAM_NAME)
    parser.add_argument("input_gmp_path")
    parser.add_argument("platform")
    parser.add_argument("tgt_gmp_path")
    args = parser.parse_args()

    if (not args.input_gmp_path or not args.tgt_gmp_path
        or args.platform.lower() not in PLATFORMS):
        print("Usage: python [program path] [gmp path] [platform=pc,psx] [target gmp path]")
        sys.exit(-1)

    # get input gmp path
    if ("\\" not in args.input_gmp_path and "/" not in args.input_gmp_path):
        input_gmp_path = ROOT_DIR / args.input_gmp_path
    else:
        input_gmp_path = Path(args.input_gmp_path)

    # get target gmp path
    if ("\\" not in args.tgt_gmp_path and "/" not in args.tgt_gmp_path):
        tgt_gmp_path = ROOT_DIR / args.tgt_gmp_path
    else:
        tgt_gmp_path = Path(args.tgt_gmp_path)

    # verify if the input gmp map exists
    if (not input_gmp_path.exists()):
        print(f"Input gmp file doesn't exists. Path: {input_gmp_path}")
        sys.exit(-1)

    # verify if the target gmp map exists
    if (not tgt_gmp_path.exists()):
        print(f"Target gmp file doesn't exists. Path: {tgt_gmp_path}")
        sys.exit(-1)

    if args.platform.lower() == "psx":
        is_psx = True
    else:
        is_psx = False
    
    print(f"\nOpening file {input_gmp_path}...\n")
    chunk_infos = detect_headers_and_get_chunks(input_gmp_path, is_psx)
    block_info_array = uncompress_gmp(input_gmp_path, chunk_infos, is_psx)

    print(f"\nOpening file {tgt_gmp_path}...\n")
    tgt_chunk_infos = detect_headers_and_get_chunks(tgt_gmp_path, False)

    if tgt_chunk_infos["UMAP"][0] is None:
        print("ERROR: This program only supports target gmps with UMAP section.")
        sys.exit(-1)

    # creating a copy of the target gmp

    filename = get_filename(tgt_gmp_path)
    output_path = ROOT_DIR / f"{filename}_injected.gmp"

    print(f"Creating copy of {filename}.gmp")
    shutil.copyfile(tgt_gmp_path, output_path)

    # now inject the block info into output
    print("Injecting block info...")
    write_uncompressed_map(output_path, tgt_chunk_infos, block_info_array)

        


if __name__ == "__main__":
    main()