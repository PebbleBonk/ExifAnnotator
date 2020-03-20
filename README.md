# Annotator tool for extracting exif data from images
Developed as a helper for a automatic cropping tool project. Developed with Python 3.7.4.

## Requirements:
1. Install `Exiftool`
2. Install `pyexiftool`

**NOTE:**
> Manual fork from `pyexiftool` was used due some crash, hence it is not included in
`requirements.txt`

 ## Running
 Run the script with at least source directory provided, e.g.:

 ```
$ python annotator.py ./images
 ```

Run `python annotator.py --help` for more options
