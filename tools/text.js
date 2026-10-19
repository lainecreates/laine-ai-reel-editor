// On-screen text in a folder of JPEG frames, using Apple's Vision framework via
// JavaScript for Automation (built into macOS; nothing to install).
//   osascript -l JavaScript tools/text.js <folder>
// Prints JSON {"frame_0001.jpg": [{"text": "...", "conf": 0.9, "box": [x, y, w, h]}, ...]}
// Boxes are normalised 0..1, origin at the TOP-left. Used only to MEASURE a
// reference reel's style (where text sits, how big, how many words); the text
// itself is kept solely to make sure it is never reused.
ObjC.import('Foundation');
ObjC.import('Vision');

function run(argv) {
    const dir = argv[0] || '.';
    const fm = $.NSFileManager.defaultManager;
    const names = ObjC.deepUnwrap(fm.contentsOfDirectoryAtPathError(dir, null)) || [];
    const out = {};
    names.filter(n => n.endsWith('.jpg')).sort().forEach(name => {
        const url = $.NSURL.fileURLWithPath(dir + '/' + name);
        const req = $.VNRecognizeTextRequest.alloc.init;
        req.recognitionLevel = 0;          // accurate: stylised caption fonts need it
        req.usesLanguageCorrection = false;
        const handler = $.VNImageRequestHandler.alloc.initWithURLOptions(url, $({}));
        handler.performRequestsError($([req]), null);
        const res = req.results;
        const items = [];
        for (let i = 0; i < res.count; i++) {
            const obs = res.objectAtIndex(i);
            const cand = obs.topCandidates(1);
            if (!cand.count) continue;
            const top = cand.objectAtIndex(0);
            const b = obs.boundingBox;
            const r = v => Math.round(v * 10000) / 10000;
            items.push({ text: ObjC.unwrap(top.string), conf: r(top.confidence),
                         box: [r(b.origin.x), r(1 - b.origin.y - b.size.height), r(b.size.width), r(b.size.height)] });
        }
        out[name] = items;
    });
    return JSON.stringify(out);
}
