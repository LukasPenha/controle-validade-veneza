document.addEventListener('DOMContentLoaded', function () {
    const buscarManualmenteBtn = document.getElementById('btnBuscarBarcode');
    const btnIniciar = document.getElementById('btnIniciarScan');

    if (!buscarManualmenteBtn || !btnIniciar) {
        return; 
    }

    if (typeof ZXing === 'undefined') {
        const statusBuscaCheck = document.getElementById('statusBusca');
        if (statusBuscaCheck) {
            statusBuscaCheck.textContent = 'Erro: A biblioteca de scanner não pôde ser carregada.';
            btnIniciar.disabled = true;
        }
        return;
    }

    const statusBusca = document.getElementById('statusBusca');
    const nomeInput = document.getElementById('nome_produto');
    const pluInput = document.getElementById('plu');
    const barcodeInput = document.getElementById('barcodeInput');
    const barcodeFormInput = document.getElementById('barcodeFormInput');
    const videoElement = document.getElementById('video');
    const btnParar = document.getElementById('btnPararScan');
    const currentUserRole = document.getElementById('currentUserRole').value;
    const privilegedRoles = ['gerente', 'gerente_geral'];

    const hints = new Map();
    const formats = [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.CODE_128, ZXing.BarcodeFormat.EAN_8, ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.ITF];
    hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, formats);
    hints.set(ZXing.DecodeHintType.TRY_HARDER, true);

    const codeReader = new ZXing.BrowserMultiFormatReader(hints);
    let selectedDeviceId;

    barcodeInput.addEventListener('input', function() {
        barcodeFormInput.value = this.value;
    });

    const setFieldsReadOnly = (isReadOnly) => {
        if (!privilegedRoles.includes(currentUserRole)) {
            pluInput.readOnly = isReadOnly;
        }
    };

    function pararScanner() {
        codeReader.reset();
        if (videoElement.srcObject) {
            videoElement.srcObject.getTracks().forEach(track => track.stop());
        }
        videoElement.style.display = 'none';
        btnParar.style.display = 'none';
        btnIniciar.style.display = 'inline-block';
        btnIniciar.disabled = false;
    }

    function buscarInformacoesDoProduto() {
        const barcode = barcodeInput.value;
        if (!barcode) { 
            statusBusca.textContent = 'Digite ou escaneie um código para buscar.';
            return; 
        }
        statusBusca.textContent = 'Buscando informações do produto...';
        buscarManualmenteBtn.disabled = true;
        fetch(`/api/buscar-produto/${barcode}`)
            .then(response => response.json())
            .then(data => {
                statusBusca.textContent = data.encontrado ? `Encontrado: ${data.fonte}` : data.mensagem;
                if (data.encontrado) {
                    nomeInput.value = data.nome;
                    pluInput.value = data.plu || ''; // Preenche o PLU se vier do catálogo interno
                    setFieldsReadOnly(true); // Trava o campo após encontrar
                } else {
                    setFieldsReadOnly(false); // Destrava se não encontrar
                }
            })
            .finally(() => {
                buscarManualmenteBtn.disabled = false;
            });
    }

    buscarManualmenteBtn.addEventListener('click', buscarInformacoesDoProduto);

    btnIniciar.addEventListener('click', () => {
        btnIniciar.disabled = true;
        statusBusca.textContent = "Iniciando câmera...";
        codeReader.listVideoInputDevices()
            .then((videoInputDevices) => {
                if (videoInputDevices.length === 0) { throw new Error("Nenhuma câmera encontrada."); }
                selectedDeviceId = videoInputDevices[0].deviceId;
                
                videoElement.style.display = 'block';
                btnIniciar.style.display = 'none';
                btnParar.style.display = 'inline-block';
                statusBusca.textContent = "Aponte o código de barras para a câmera...";

                codeReader.decodeFromVideoDevice(selectedDeviceId, 'video', (result, err) => {
                    if (result) {
                        pararScanner();
                        barcodeInput.value = result.text;
                        barcodeFormInput.value = result.text;
                        buscarInformacoesDoProduto();
                    }
                    if (err && !(err instanceof ZXing.NotFoundException)) {
                        statusBusca.textContent = "Ocorreu um erro ao escanear.";
                        pararScanner();
                    }
                });
            })
            .catch(err => {
                statusBusca.textContent = `Erro: ${err.message}`;
                btnIniciar.disabled = false;
            });
    });

    btnParar.addEventListener('click', () => {
        statusBusca.textContent = "Scanner parado pelo usuário.";
        pararScanner();
    });
});