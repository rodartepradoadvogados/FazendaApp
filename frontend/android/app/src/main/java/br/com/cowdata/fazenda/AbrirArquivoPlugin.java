package br.com.cowdata.fazenda;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;

import androidx.core.content.FileProvider;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.File;

/**
 * Abre um arquivo do cache do app (PDF gerado no celular) no visualizador do
 * Android. É o que faz o botão "Exportar PDF" do app mostrar o arquivo: a
 * WebView não baixa nada sozinha (ver lib/nativo.ts::salvarArquivo). Usa o
 * FileProvider já declarado no AndroidManifest (cache-path em file_paths.xml).
 */
@CapacitorPlugin(name = "AbrirArquivo")
public class AbrirArquivoPlugin extends Plugin {

    @PluginMethod
    public void abrir(PluginCall call) {
        String uriTexto = call.getString("uri");
        String mime = call.getString("mime", "application/pdf");
        if (uriTexto == null || uriTexto.isEmpty()) {
            call.reject("uri obrigatório");
            return;
        }
        try {
            String caminho = Uri.parse(uriTexto).getPath();
            if (caminho == null) {
                call.reject("uri inválido");
                return;
            }
            File arquivo = new File(caminho);
            if (!arquivo.exists()) {
                call.reject("arquivo não encontrado");
                return;
            }
            Uri conteudo = FileProvider.getUriForFile(
                getContext(), getContext().getPackageName() + ".fileprovider", arquivo);
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(conteudo, mime);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(intent);
            call.resolve(new JSObject());
        } catch (ActivityNotFoundException e) {
            call.reject("sem_visualizador");
        } catch (Exception e) {
            call.reject("falha ao abrir: " + e.getMessage());
        }
    }
}
