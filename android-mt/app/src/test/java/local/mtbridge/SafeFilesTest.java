package local.mtbridge;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;

public class SafeFilesTest {
    @Test public void quotesShellMetacharactersAsData() throws Exception {
        assertEquals("'/a'\"'\"'b/$(id);`x` file'", SafeFiles.quotePath("/a'b/$(id);`x` file"));
    }
    @Test public void rejectsRelativeAndControlPaths() {
        for (String value : new String[]{"relative.json", "/a\nb", "/a\0b", "/a\rb"}) {
            try { SafeFiles.quotePath(value); fail(value); } catch (IOException expected) {}
        }
    }
    @Test public void boundedReads() throws Exception {
        assertArrayEquals(new byte[]{1,2,3}, SafeFiles.readLimited(new ByteArrayInputStream(new byte[]{1,2,3})));
        try { SafeFiles.readLimited(new ByteArrayInputStream(new byte[SafeFiles.LIMIT+1])); fail(); }
        catch (IOException expected) { assertEquals("MTB_TOO_LARGE", expected.getMessage()); }
    }
}
