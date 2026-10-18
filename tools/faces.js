// Face boxes for a folder of JPEG frames, using Apple's Vision framework via
// JavaScript for Automation (built into macOS; nothing to install).
//   osascript -l JavaScript tools/faces.js <folder>
// Prints JSON {"frame_0001.jpg": [[x, y, w, h], ...]} - boxes normalised
// 0..1, origin at the TOP-left.
ObjC.import('Foundation');
ObjC.import('Vision');

function run(argv) {
    const dir = argv[0] || '.';
    const fm = $.NSFileManager.defaultManager;
    const names = ObjC.deepUnwrap(fm.contentsOfDirectoryAtPathError(dir, null)) || [];
    const out = {};
    names.filter(n => n.endsWith('.jpg')).sort().forEach(name => {
        const url = $.NSURL.fileURLWithPath(dir + '/' + name);
        const req = $.VNDetectFaceRectanglesRequest.alloc.init;
        const handler = $.VNImageRequestHandler.alloc.initWithURLOptions(url, $({}));
        handler.performRequestsError($([req]), null);
        const res = req.results;
        const boxes = [];
        for (let i = 0; i < res.count; i++) {
            const b = res.objectAtIndex(i).boundingBox;
            const r = v => Math.round(v * 10000) / 10000;
            boxes.push([r(b.origin.x), r(1 - b.origin.y - b.size.height),
                        r(b.size.width), r(b.size.height)]);
        }
        out[name] = boxes;
    });
    return JSON.stringify(out);
}
