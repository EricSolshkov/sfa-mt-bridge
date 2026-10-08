package local.mtbridge;

import android.util.Base64;
import java.io.*;
import java.net.*;
import javax.net.ssl.HttpsURLConnection;
import java.util.function.Consumer;

/** Narrow interface called only by the bundled converter, never by remote content. */
public final class NativeBridge {
    private final boolean root;
    private final Consumer<String> progress;
    public NativeBridge(boolean root, Consumer<String> progress) { this.root = root; this.progress = progress; }
    public void progress(String message) { progress.accept(message); }
    public String readBase64(String path) throws IOException {
        return Base64.encodeToString(SafeFiles.read(path, root), Base64.NO_WRAP);
    }
    public String fetchBase64(String url, String userAgent) throws IOException {
        try {
            URL current = new URL(url);
            for (int i = 0; i < 6; i++) {
                if (!current.getProtocol().equals("https")) throw new IOException("MTB_HTTPS_REQUIRED");
                HttpsURLConnection connection = (HttpsURLConnection) current.openConnection(Proxy.NO_PROXY);
                connection.setConnectTimeout(40000);
                connection.setReadTimeout(40000);
                connection.setInstanceFollowRedirects(false);
                connection.setRequestProperty("User-Agent", userAgent);
                connection.setRequestProperty("Accept-Encoding", "identity");
                try {
                    int status = connection.getResponseCode();
                    if (status == 301 || status == 302 || status == 303 || status == 307 || status == 308) {
                        String location = connection.getHeaderField("Location");
                        if (location == null) throw new IOException("MTB_BAD_REDIRECT");
                        current = new URL(current, location);
                        continue;
                    }
                    if (status != 200) throw new IOException("MTB_HTTP:" + status);
                    if (connection.getContentLengthLong() > SafeFiles.LIMIT) throw new IOException("MTB_TOO_LARGE");
                    try (InputStream in = connection.getInputStream()) {
                        return Base64.encodeToString(SafeFiles.readLimited(in), Base64.NO_WRAP);
                    }
                } finally { connection.disconnect(); }
            }
            throw new IOException("MTB_REDIRECT_LIMIT");
        } catch (IOException e) {
            if (e.getMessage() != null && e.getMessage().matches("MTB_[A-Z_]+(:[0-9]+)?")) throw e;
            if (e instanceof javax.net.ssl.SSLException) throw new IOException("MTB_TLS_FAILED");
            if (e instanceof SocketTimeoutException) throw new IOException("MTB_NETWORK_TIMEOUT");
            if (e instanceof UnknownHostException) throw new IOException("MTB_DNS_FAILED");
            throw new IOException("MTB_NETWORK_FAILED");
        } catch (IllegalArgumentException e) { throw new IOException("MTB_INVALID_URL_OR_HEADER"); }
    }
}
