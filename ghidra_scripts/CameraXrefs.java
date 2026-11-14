// Reports which functions reference the camera-related strings in RetailOS.
// Run headless with -postScript CameraXrefs.java, or from Ghidra's Script Manager.
//@category NanoCam

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class CameraXrefs extends GhidraScript {

	private static final String[] TARGETS = {
		"Video Camera",
		"controller.CameraSelected",
		"CameraSelected",
		"GKImageCaptureThread",
		"JPEGEncodeThread",
		"JPEGPreprocessThread",
		"CameraShutter",
		"Resources/Sounds/camera.wav",
		"cameraremote.photo.up",
		"cameraremote.video.up",
		"StartRecord",
		"GKCameraDriver - camera overflow occurred!",
	};

	@Override
	protected void run() throws Exception {
		println("functions: " + currentProgram.getFunctionManager().getFunctionCount());
		for (String target : TARGETS) {
			// Match the string plus its NUL terminator so "CameraSelected" doesn't hit longer names.
			byte[] needle = (target + "\0").getBytes("US-ASCII");
			Address addr = currentProgram.getMinAddress();
			while ((addr = currentProgram.getMemory().findBytes(addr, needle, null, true, monitor)) != null) {
				// Skip matches that are the tail of a longer string.
				byte before = addr.equals(currentProgram.getMinAddress()) ? 0
						: currentProgram.getMemory().getByte(addr.subtract(1));
				if (before < 0x20 || before > 0x7e) {
					report(target, addr);
				}
				addr = addr.add(1);
			}
		}
	}

	private void report(String target, Address addr) {
		Reference[] refs = getReferencesTo(addr);
		println(String.format("%-45s @ %s  refs=%d", target, addr, refs.length));
		for (Reference ref : refs) {
			Function fn = getFunctionContaining(ref.getFromAddress());
			println(String.format("    from %s in %s", ref.getFromAddress(),
				fn == null ? "(no function)" : fn.getName() + " @ " + fn.getEntryPoint()));
		}
	}
}
