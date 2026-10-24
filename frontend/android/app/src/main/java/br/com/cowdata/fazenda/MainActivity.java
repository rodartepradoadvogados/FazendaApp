package br.com.cowdata.fazenda;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Plugins próprios precisam ser registrados antes do super.onCreate.
        registerPlugin(AbrirArquivoPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
