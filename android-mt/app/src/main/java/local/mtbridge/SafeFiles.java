package local.mtbridge;

import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Only bounded, read-only file operations run through su. Never runs user commands. */
public final class SafeFiles {
    public static final int LIMIT = 20 * 1024 * 1024;
    private SafeFiles() {}

    public static String quotePath(String path) throws IOException {
        if (path == null || !path.startsWith("/") || path.indexOf('\0') >= 0 ||
                path.indexOf('\n') >= 0 || path.indexOf('\r') >= 0 || path.length() > 4096)
            throw new IOException("MTB_INVALID_PATH");
        return "'" + path.replace("'", "'\"'\"'") + "'";
    }

    public static byte[] readLimited(InputStream input) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[16384];
        int n;
        while ((n = input.read(buffer)) != -1) {
            if (out.size() + n > LIMIT) throw new IOException("MTB_TOO_LARGE");
            out.write(buffer, 0, n);
        }
        return out.toByteArray();
    }

    public static byte[] read(String path, boolean root) throws IOException {
        String quoted = quotePath(path);
        if (!root) {
            File file = new File(path);
            if (!file.isFile()) throw new IOException("MTB_FILE_UNAVAILABLE");
            try (InputStream in = new FileInputStream(file)) { return readLimited(in); }
            catch (FileNotFoundException e) { throw new IOException("MTB_PERMISSION_OR_PATH"); }
        }
        Process process;
        try {
            // Android app-data isolation survives UID 0 in the app's mount namespace.
            // KernelSU/Magisk mount-master exposes the real /data/user/0 tree.
            process = new ProcessBuilder("su", "-M", "-c",
                "[ -f " + quoted + " ] || exit 44; exec /system/bin/cat -- " + quoted).start();
        } catch (IOException e) { throw new IOException("MTB_SU_UNAVAILABLE"); }
        AtomicBoolean timedOut = new AtomicBoolean();
        ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
        timer.schedule(() -> { timedOut.set(true); process.destroyForcibly(); }, 45, TimeUnit.SECONDS);
        Thread drain = new Thread(() -> {
            try (InputStream err = process.getErrorStream()) {
                byte[] discard = new byte[1024];
                while (err.read(discard) != -1) { /* never surface arbitrary su stderr */ }
            } catch (IOException ignored) {}
        }, "root-stderr");
        drain.setDaemon(true);
        drain.start();
        try (InputStream in = process.getInputStream()) {
            process.getOutputStream().close();
            byte[] data = readLimited(in);
            int code = process.waitFor();
            if (timedOut.get()) throw new IOException("MTB_ROOT_TIMEOUT");
            if (code == 44) throw new IOException("MTB_FILE_UNAVAILABLE");
            if (code != 0) throw new IOException("MTB_ROOT_DENIED_OR_READ_FAILED");
            return data;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("MTB_CANCELLED");
        } catch (IOException e) {
            if (timedOut.get()) throw new IOException("MTB_ROOT_TIMEOUT");
            throw e;
        } finally {
            timer.shutdownNow();
            process.destroyForcibly();
        }
    }
}
