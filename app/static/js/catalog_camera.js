document.addEventListener('DOMContentLoaded', () => {
    const start = document.getElementById('cameraStart');
    if (!start) return;
    const stop = document.getElementById('cameraStop');
    const video = document.getElementById('catalogVideo');
    const status = document.getElementById('cameraStatus');
    const input = document.getElementById('productSearchInput');
    let reader;
    let generation = 0;
    const close = () => {
        generation++;
        reader?.reset();
        video.srcObject?.getTracks().forEach(track => track.stop());
        video.srcObject = null;
        video.hidden = true;
        stop.hidden = true;
        start.disabled = false;
    };
    start.addEventListener('click', async () => {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
            status.textContent = 'A câmera precisa de HTTPS e de um navegador compatível. Você também pode digitar o código.';
            return;
        }
        if (typeof ZXing === 'undefined') {
            status.textContent = 'O leitor não carregou. Atualize a página ou digite o código.';
            return;
        }
        start.disabled = true;
        stop.hidden = false;
        video.hidden = false;
        status.textContent = 'Permita o acesso à câmera e aproxime o código de barras.';
        const currentGeneration = ++generation;
        reader = new ZXing.BrowserMultiFormatReader();
        try {
            await reader.decodeFromConstraints({audio:false, video:{facingMode:{ideal:'environment'}, width:{ideal:1280}, height:{ideal:720}}}, video, result => {
                if (currentGeneration !== generation || !result) return;
                const code = result.getText();
                close();
                input.value = code;
                input.dispatchEvent(new Event('barcode-scanned', {bubbles:true}));
                status.textContent = `Código lido: ${code}. Selecione o produto abaixo.`;
            });
            if (currentGeneration !== generation) close();
        } catch (error) {
            close();
            status.textContent = error.name === 'NotAllowedError'
                ? 'Acesso negado. Libere a câmera nas permissões do navegador ou digite o código.'
                : 'Não foi possível abrir a câmera. Verifique se está em uso em outro aplicativo.';
        }
    });
    stop.addEventListener('click', () => { close(); status.textContent = 'Câmera fechada.'; });
    window.addEventListener('pagehide', close);
    document.addEventListener('visibilitychange', () => { if (document.hidden) close(); });
});
