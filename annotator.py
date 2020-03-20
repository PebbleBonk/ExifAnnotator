from pathlib import Path
from joblib import Parallel, delayed
import multiprocessing
import imageio
import json
import glob
import os

from tqdm import tqdm
from PIL import Image
import pyexiftool.exiftool as pet
import rawpy
import fire


def extract_crop_data_from_exif(exif_data, extractables):
    """ Extract wanted exif data from a file """
    exif = {}
    for k, v in extractables.items():
        exif[k] = exif_data.get(*v)

   #print(json.dumps(exif, indent=4))

    # A coefficient showing the relative amount cropped:
    exif['CropFactor'] = (exif['CropLeft'] + (1-exif['CropRight']) +
                 exif['CropTop']  + (1-exif['CropBottom']))/4

    # HACK: set filename based on do we have xmp or photo:
    if exif['ExifFileName'].lower().endswith('.xmp'):
        exif['PhotoFileName'] = exif['RawFileName']
    else:
        exif['PhotoFileName'] = exif['ExifFileName']

    return exif


def resize_photo(im_name, dest_dir, dim_max, quality, **kwargs):
    """ Save a resized photo as jpg """

    # XXX: Ugly:
    p = Path(os.path.join(kwargs.get('dir', ''), im_name))

    # RAW image:
    try:
        with rawpy.imread(im_name) as raw:
            rgb = raw.postprocess()
    # Normal image:
    except rawpy.LibRawFileUnsupportedError:
        rgb = imageio.imread(im_name)
    # Photo not found:
    except rawpy.LibRawIOError:
        return None

    # Resize:
    im = Image.fromarray(rgb)
    r = dim_max/max(im.width, im.height)
    im = Image.fromarray(rgb)
    im = im.resize((int(im.width*r), int(im.height*r)))

    # Save:
    new_im_name = p.stem+'.jpg'
    im.save(dest_dir+new_im_name, quality=quality)

    return new_im_name


def resize_saver(crop_data, settings):
    """ Resize and save a photo from crop data with settings """
    # Resize and save:
    crop_data['FileName'] = resize_photo(
        os.path.join(settings['dir'], crop_data['PhotoFileName']),
        **settings
    )

    # Save information about the new image:
    crop_data.update(settings)

    return crop_data


def list_exif_sources(source_dir):
    """ Scan a directory, return names of photos with exif info
        1. XMP + separate photo file
        2. Photo files supporting embedded XMP
        3. Unsupported images only

        Return:
            list: exif_files
    """
    # Use a hierarchy for files:
    extensions = [
        # Major photo formats
        '*.png', '*.jpg', '*.jpeg', '*.tiff', '*.gif', '*.dng'
        # (Raw files not suportted)
    ]

    # Note: glob is case insensitive:
    exif_files = glob.glob(os.path.join(source_dir,'*.xmp'))

    # Case 2: XMP embedded in photos:
    for ext in extensions:
        photo_files = glob.glob(os.path.join(source_dir,ext))
        if len(photo_files):
            exif_files += photo_files

    if len(exif_files):
        return exif_files
    return None


def extract_exif_from_dir(source_dir, extractables):
    # List files with exif data:
    exif_files = list_exif_sources(source_dir)
    if exif_files is None:
        return None

    # Initialise counters and arrays:
    cropped_photo_exifs = []
    cropped, uncropped = 0, 0

    # Loop 1: Extract the exif data for cropped photos:
    with pet.ExifTool(executable_='exiftool') as et:
        for ef in tqdm(exif_files):
            # Load the exif data:
            exif_data = et.get_metadata(ef)
            # Extract the crop datas:
            crop_data = extract_crop_data_from_exif(exif_data, extractables)

            # If we do not have crop data, skip:
            if crop_data['CropFactor'] <= 0:
                uncropped += 1
                continue
            else:
                cropped += 1
            cropped_photo_exifs.append(crop_data)

    print("Found cropped images:", cropped)
    print("Found uncropped images:", uncropped)
    return cropped_photo_exifs


def resize_serial(cropped_photo_exifs, settings):
    # Create the destination directory if necessary:
    if not os.path.exists(settings['dest_dir']):
        os.makedirs(settings['dest_dir'])

    annotations = []
    for crop_data in tqdm(cropped_photo_exifs):
        # Resize and save:
        updated_data = resize_saver(crop_data, settings)
        annotations.append(updated_data)
    return annotations


def resize_parallel(cropped_photo_exifs, settings):
    # Create the destination directory if necessary:
    if not os.path.exists(settings['dest_dir']):
        os.makedirs(settings['dest_dir'])

    exifs = tqdm(cropped_photo_exifs)

    annotations = Parallel(n_jobs=-1)(
        delayed(resize_saver)(cd, settings) for cd in exifs
    )
    return annotations


def main(source_dir, parallel=True, save=False, config_file='config.json'):
    """
    Scan a directory for images with exif data on crops  \n
    Resizes and saves those images to another folder.

    :param source_dir name of the user
    :param parallel Run multithreaded (default: True)
    :param save Save the results? (default: True)
    :param config_file File containing the config (default: config.json)
    """
    with open(config_file, 'r') as f:
        config = json.load(f)

    settings = config['SETTINGS']
    settings['dir'] = source_dir
    extractables = config['EXTRACTABLES']
    annotation_file =  config.get('ANNOTATIONS_FILE', 'labels.json')

    print('--- Scan for EXIF / XMP information: ---')
    photo_exifs = extract_exif_from_dir(source_dir, extractables)
    if photo_exifs is None:
        print('No supported images or exif files found:', source_dir)
        return

    if save:
        print('--- Resize and save images with crop information: ---')
        if parallel:
            annotations = resize_parallel(photo_exifs, settings)
        else:
            annotations = resize_serial(photo_exifs, settings)

        print("Images not found:",
              len([p for p in annotations if p['FileName'] is None])
        )
        print("Images found, resized and saved:",
              len([p for p in annotations if p['FileName'] is not None])
        )

        with open(annotation_file, 'w') as f:
            json.dump(annotations, f, indent=4)
        print("Saved annotations to", annotation_file)
    else:
        print("Did not save the annotations")

    print('DONE!')


if __name__ == "__main__":
    fire.Fire(main)