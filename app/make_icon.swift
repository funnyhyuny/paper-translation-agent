// 앱 아이콘 생성: 크림색 종이 위의 적갈색 하트 도장.
// 사용: make_icon <출력.iconset>
import AppKit

func drawIcon(size: CGFloat) -> Data {
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size), bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
    )!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let s = size / 1024

    // macOS 아이콘 격자: 824pt 본체, 가장자리 100pt 여백
    let plate = NSRect(x: 100 * s, y: 100 * s, width: 824 * s, height: 824 * s)
    let shape = NSBezierPath(roundedRect: plate, xRadius: 185 * s, yRadius: 185 * s)
    NSColor(red: 0.965, green: 0.941, blue: 0.894, alpha: 1).setFill()
    shape.fill()

    // 겹쳐 놓은 종이
    let back = NSBezierPath(rect: NSRect(x: 318 * s, y: 212 * s, width: 420 * s, height: 580 * s))
    NSColor(red: 0.902, green: 0.863, blue: 0.788, alpha: 1).setFill()
    back.fill()
    let sheetRect = NSRect(x: 286 * s, y: 244 * s, width: 420 * s, height: 580 * s)
    NSColor(red: 1, green: 0.992, blue: 0.973, alpha: 1).setFill()
    NSBezierPath(rect: sheetRect).fill()
    NSColor(red: 0.878, green: 0.835, blue: 0.761, alpha: 1).setFill()
    for i in 0..<4 {
        NSBezierPath(rect: NSRect(x: 340 * s, y: (712 - CGFloat(i) * 44) * s, width: (i == 3 ? 190 : 312) * s, height: 14 * s)).fill()
    }

    // 하트
    let cx = 496 * s, top = 500 * s, w = 150 * s
    let heart = NSBezierPath()
    heart.move(to: NSPoint(x: cx, y: 300 * s))
    heart.curve(to: NSPoint(x: cx - w, y: top), controlPoint1: NSPoint(x: cx - 60 * s, y: 360 * s), controlPoint2: NSPoint(x: cx - w, y: 420 * s))
    heart.curve(to: NSPoint(x: cx, y: top), controlPoint1: NSPoint(x: cx - w, y: 590 * s), controlPoint2: NSPoint(x: cx - 30 * s, y: 590 * s))
    heart.curve(to: NSPoint(x: cx + w, y: top), controlPoint1: NSPoint(x: cx + 30 * s, y: 590 * s), controlPoint2: NSPoint(x: cx + w, y: 590 * s))
    heart.curve(to: NSPoint(x: cx, y: 300 * s), controlPoint1: NSPoint(x: cx + w, y: 420 * s), controlPoint2: NSPoint(x: cx + 60 * s, y: 360 * s))
    heart.close()
    NSColor(red: 0.612, green: 0.239, blue: 0.180, alpha: 1).setFill()
    heart.fill()

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])!
}

let out = URL(fileURLWithPath: CommandLine.arguments[1])
try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
for base in [16, 32, 128, 256, 512] {
    try drawIcon(size: CGFloat(base)).write(to: out.appendingPathComponent("icon_\(base)x\(base).png"))
    try drawIcon(size: CGFloat(base * 2)).write(to: out.appendingPathComponent("icon_\(base)x\(base)@2x.png"))
}
