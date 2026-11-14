// Guesses the RetailOS load address.
// Code loads absolute pointers from literal pools (ldr rX, [pc, #n]). If the image is
// loaded at the wrong base, those pointers land outside it. This script collects every
// literal-pool value, then scores candidate bases by how many values would then point at
// the start of a string in the image.
//@category iPodCamera

import java.util.*;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

public class GuessBase extends GhidraScript {

	@Override
	protected void run() throws Exception {
		Memory mem = currentProgram.getMemory();
		long size = currentProgram.getMaxAddress().getOffset() + 1;

		// Values loaded from literal pools.
		List<Long> values = new ArrayList<>();
		for (Instruction insn : currentProgram.getListing().getInstructions(true)) {
			if (!insn.getMnemonicString().toLowerCase().startsWith("ldr")) {
				continue;
			}
			for (Reference ref : insn.getReferencesFrom()) {
				if (ref.getReferenceType().isRead()) {
					try {
						values.add(mem.getInt(ref.getToAddress()) & 0xffffffffL);
					}
					catch (Exception e) {
						// Reference points outside the image.
					}
				}
			}
		}
		println("literal-pool values: " + values.size());

		// Histogram of the top 12 bits shows where the pointers cluster.
		Map<Long, Integer> hist = new TreeMap<>();
		for (long v : values) {
			hist.merge(v >>> 20, 1, Integer::sum);
		}
		hist.entrySet().stream()
			.sorted((a, b) -> b.getValue() - a.getValue())
			.limit(12)
			.forEach(e -> println(String.format("  %08x..: %d", e.getKey() << 20, e.getValue())));

		// Offsets of string starts: a printable run of 4+ bytes after a NUL.
		byte[] image = new byte[(int) size];
		mem.getBytes(currentProgram.getMinAddress(), image);
		Set<Long> starts = new HashSet<>();
		for (int i = 1; i + 4 < image.length; i++) {
			if (image[i - 1] == 0 && printable(image[i]) && printable(image[i + 1]) &&
				printable(image[i + 2]) && printable(image[i + 3])) {
				starts.add((long) i);
			}
		}

		// Vote: each value could point at each string start, implying base = value - start.
		// Only bases aligned to 4 KB are counted, which keeps this fast and is how
		// firmware is normally linked.
		Map<Long, Integer> votes = new HashMap<>();
		for (long v : values) {
			for (long base = (v - size) & ~0xfffL; base <= v; base += 0x1000) {
				if (base >= 0 && starts.contains(v - base)) {
					votes.merge(base, 1, Integer::sum);
				}
			}
			if (monitor.isCancelled()) {
				return;
			}
		}
		println("best bases:");
		votes.entrySet().stream()
			.sorted((a, b) -> b.getValue() - a.getValue())
			.limit(8)
			.forEach(e -> println(String.format("  %08x: %d literal values hit a string start", e.getKey(), e.getValue())));
	}

	private static boolean printable(byte b) {
		return b >= 0x20 && b <= 0x7e;
	}
}
