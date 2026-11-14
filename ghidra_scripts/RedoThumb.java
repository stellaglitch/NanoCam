// Re-disassembles an address range as Thumb, for code Ghidra wrongly decoded as ARM.
// Headless usage: -postScript RedoThumb.java <hex start> <hex end>
// Combine with -readOnly and a following -postScript Decompile.java to try it without saving.
//@category NanoCam

import java.math.BigInteger;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class RedoThumb extends GhidraScript {

	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		Address start = toAddr(Long.parseLong(args[0].replace("0x", ""), 16));
		Address end = toAddr(Long.parseLong(args[1].replace("0x", ""), 16));

		Instruction first = getInstructionContaining(start);
		clearListing(first != null ? first.getMinAddress() : start, end);
		Register tmode = currentProgram.getProgramContext().getRegister("TMode");
		currentProgram.getProgramContext().setValue(tmode, start, end, BigInteger.ONE);
		disassemble(start);

		Function fn = getFunctionBefore(start.add(1));
		if (fn != null) {
			ghidra.app.cmd.function.CreateFunctionCmd.fixupFunctionBody(currentProgram, fn, monitor);
		}
		println("re-disassembled " + start + ".." + end + " as Thumb");
	}
}
