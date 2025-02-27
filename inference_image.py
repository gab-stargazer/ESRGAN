import argparse
import glob
import os

import cv2
import torch
from facexlib import load_file_from_url
from realesrgan import RealESRGANer

import util.model_decider
from util.timer import Stopwatch


def main():
    if not torch.cuda.is_available():
        print('Error: This project is intended to only works with CUDA capable device')
        return

    # Parse all the arguments before doing anything
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--input',
        type=str,
        default='inputs',
        help='Input image or folder'
    )

    parser.add_argument(
        '-n', '--model_name',
        type=str,
        default='RealESRGAN_x4plus',
        help=(
            'Model names: RealESRGAN_x4plus | '
            'RealESRNet_x4plus | '
            'RealESRGAN_x4plus_anime_6B | '
            'RealESRGAN_x2plus | '
            'realesr-animevideov3 | '
            'realesr-general-x4v3')
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        default='results',
        help='Output folder'
    )

    parser.add_argument(
        '-dn',
        '--denoise_strength',
        type=float,
        default=0.5,
        help='Denoise strength. 0 for weak denoise (keep noise), 1 for strong denoise ability. Only used for the realesr-general-x4v3 model')

    parser.add_argument(
        '-s', '--outscale',
        type=int,
        default=2,
        help='The final upsampling scale of the image'
    )

    parser.add_argument(
        '--model_path',
        type=str,
        default=None,
        help='[Option] Model path. Usually, you do not need to specify it'
    )

    parser.add_argument(
        '--suffix',
        type=str,
        default='out',
        help='Suffix of the restored image'
    )

    parser.add_argument(
        '-t', '--tile',
        type=int,
        default=0,
        help='Tile size, 0 for no tile during testing'
    )

    parser.add_argument(
        '--tile_pad',
        type=int,
        default=10,
        help='Tile padding'
    )

    parser.add_argument(
        '--pre_pad',
        type=int,
        default=0,
        help='Pre padding size at each border'
    )

    parser.add_argument(
        '--face_enhance',
        action='store_true',
        help='Use GFPGAN to enhance face'
    )

    parser.add_argument(
        '--fp32',
        action='store_true',
        help='Use fp32 precision during inference. Default: fp16 (half precision).'
    )

    parser.add_argument(
        '--alpha_upsampler',
        type=str,
        default='realesrgan',
        help='The upsampler for the alpha channels. Options: realesrgan | bicubic'
    )

    parser.add_argument(
        '--ext',
        type=str,
        default='auto',
        help='Image extension. Options: auto | jpg | png, auto means using the same extension as inputs'
    )

    parser.add_argument(
        '-g', '--gpu-id',
        type=int,
        default=None,
        help='gpu device to use (default=None) can be 0,1,2 for multi-gpu'
    )

    args = parser.parse_args()

    # determine models according to model names
    args.model_name = args.model_name.split('.')[0]
    model, netscale, file_url = util.model_decider.determine_model(args.model_name)

    # determine model paths
    if args.model_path is not None:
        model_path = args.model_path
    else:
        model_path = os.path.join('weights', args.model_name + '.pth')
        if not os.path.isfile(model_path):
            ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
            for url in file_url:
                # model_path will be updated
                model_path = load_file_from_url(
                    url=url, model_dir=os.path.join(ROOT_DIR, 'weights'), progress=True, file_name=None)

    # use dni to control the denoise strength
    dni_weight = None
    if args.model_name == 'realesr-general-x4v3' and args.denoise_strength != 1:
        wdn_model_path = model_path.replace('realesr-general-x4v3', 'realesr-general-wdn-x4v3')
        model_path = [model_path, wdn_model_path]
        dni_weight = [args.denoise_strength, 1 - args.denoise_strength]

    # restorer
    upsampler = RealESRGANer(
        scale=netscale,
        model_path=model_path,
        dni_weight=dni_weight,
        model=model,
        tile=args.tile,
        tile_pad=args.tile_pad,
        pre_pad=args.pre_pad,
        half=not args.fp32,
        gpu_id=args.gpu_id)

    if args.face_enhance:  # Use GFPGAN for face enhancement
        from gfpgan import GFPGANer
        face_enhancer = GFPGANer(
            model_path='https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.3.pth',
            upscale=args.outscale,
            arch='clean',
            channel_multiplier=2,
            bg_upsampler=upsampler
        )

    os.makedirs(args.output, exist_ok=True)

    if os.path.isfile(args.input):
        paths = [args.input]
    else:
        paths = sorted(glob.glob(os.path.join(args.input, '*')))

    for idx, path in enumerate(paths):
        if os.path.isdir(path):
            continue

        imgname, extension = os.path.splitext(os.path.basename(path))

        if is_video(extension):
            continue

        print('Up-scaling', idx, imgname + extension)

        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if len(img.shape) == 3 and img.shape[2] == 4:
            img_mode = 'RGBA'
        else:
            img_mode = None

        try:
            if args.face_enhance:
                _, _, output = face_enhancer.enhance(img, has_aligned=False, only_center_face=False, paste_back=True)
            else:
                output, _ = upsampler.enhance(img, outscale=args.outscale)
        except RuntimeError as error:
            print('Error', error)
            print('If you encounter CUDA out of memory, try to set --tile with a smaller number.')
        else:
            if args.ext == 'auto':
                extension = extension[1:]
            else:
                extension = args.ext
            if img_mode == 'RGBA':  # RGBA images should be saved in png format
                extension = 'png'
            if args.suffix == '':
                save_path = os.path.join(args.output, f'{imgname}.{extension}')
            else:
                save_path = os.path.join(args.output, f'{imgname}_{args.outscale}x.{extension}')
            cv2.imwrite(save_path, output)


def is_video(filename):
    """Check if the given filename has a video extension."""
    _, ext = os.path.splitext(filename)
    video_extension = {'.mp4', '.avi', '.mov', '.wmv', '.mpeg', '.mpg', '.mkv', '.flv', '.webm'}
    return ext.lower() in video_extension


if __name__ == '__main__':
    timer = Stopwatch()
    timer.start()
    main()
    timer.stop()
    print(f"Total time: {timer.get_elapsed_time()}s")
