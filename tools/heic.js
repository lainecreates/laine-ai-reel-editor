// Convert an iPhone HEIC/HEIF photo to an upright JPEG with Apple's ImageIO via
// JavaScript for Automation (built into macOS; nothing to install).
//   osascript -l JavaScript tools/heic.js <in.heic> <out.jpg>
// The photo's rotation (EXIF orientation or the HEIF rotation box) is applied to
// the pixels, so the JPEG is upright everywhere; full size, never cropped.
// Prints JSON {"width": w, "height": h, "orientation": n}.
ObjC.import('Foundation');
ObjC.import('ImageIO');
ObjC.import('CoreGraphics');

function run(argv) {
    const src = $.CGImageSourceCreateWithURL($.NSURL.fileURLWithPath(argv[0]), null);
    if (!src || $.CGImageSourceGetCount(src) < 1) throw new Error('not a readable photo');
    const props = ObjC.deepUnwrap(ObjC.castRefToObject($.CGImageSourceCopyPropertiesAtIndex(src, 0, null))) || {};
    const w = props.PixelWidth || 0, h = props.PixelHeight || 0;
    const opts = $.NSMutableDictionary.alloc.init;
    opts.setObjectForKey($.NSNumber.numberWithBool(true), $('kCGImageSourceCreateThumbnailFromImageAlways'));
    opts.setObjectForKey($.NSNumber.numberWithBool(true), $('kCGImageSourceCreateThumbnailWithTransform'));
    opts.setObjectForKey($.NSNumber.numberWithInt(Math.max(w, h, 1)), $('kCGImageSourceThumbnailMaxPixelSize'));
    const img = $.CGImageSourceCreateThumbnailAtIndex(src, 0, opts);
    if (!img) throw new Error('could not decode the photo');
    const dst = $.CGImageDestinationCreateWithURL($.NSURL.fileURLWithPath(argv[1]), $('public.jpeg'), 1, null);
    const q = $.NSMutableDictionary.alloc.init;
    q.setObjectForKey($.NSNumber.numberWithDouble(0.92), $('kCGImageDestinationLossyCompressionQuality'));
    $.CGImageDestinationAddImage(dst, img, q);
    if (!$.CGImageDestinationFinalize(dst)) throw new Error('could not write the JPEG');
    return JSON.stringify({ width: $.CGImageGetWidth(img), height: $.CGImageGetHeight(img),
                            orientation: props.Orientation || 1 });
}
