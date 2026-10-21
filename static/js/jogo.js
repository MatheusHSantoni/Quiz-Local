const alternativas = document.querySelectorAll('input[name="alternativa"]');

alternativas.forEach((alternativa) => {
    alternativa.addEventListener("change", () => {
        document.querySelectorAll(".op").forEach((opcao) => {
            opcao.classList.remove("sel");
        });

        alternativa.closest(".op").classList.add("sel");
    });
});


const cronometroContainer = document.getElementById("cronometro-container");
const cronometro = document.getElementById("cronometro");
const formulario = document.getElementById("form-resposta");
const botaoConfirmar = document.getElementById("btn-confirmar");


function bloquearResposta() {
    alternativas.forEach((alternativa) => {
        alternativa.disabled = true;
    });

    if (botaoConfirmar) {
        botaoConfirmar.disabled = true;
        botaoConfirmar.textContent = "Tempo encerrado";
    }
}


function atualizarCronometro() {
    if (!cronometroContainer || !cronometro) {
        return;
    }

    const fimEtapa = cronometroContainer.dataset.fimEtapa;

    if (!fimEtapa) {
        return;
    }

    const horarioFim = new Date(fimEtapa).getTime();
    const agora = Date.now();

    const segundosRestantes = Math.max(
        0,
        Math.ceil((horarioFim - agora) / 1000)
    );

    const minutos = Math.floor(segundosRestantes / 60);
    const segundos = segundosRestantes % 60;

    cronometro.textContent =
        `${String(minutos).padStart(2, "0")}:${String(segundos).padStart(2, "0")}`;

    if (segundosRestantes <= 0) {
        bloquearResposta();

        return false;}

    return true;}


if (cronometroContainer) {
    const ativo = atualizarCronometro();

    if (ativo) {
        const intervalo = setInterval(() => {
            const continuaAtivo = atualizarCronometro();

            if (!continuaAtivo) {
                clearInterval(intervalo);

                setTimeout(() => {
                    window.location.reload();
                }, 1000);}
        }, 1000);}}


if (formulario && cronometroContainer) {
    formulario.addEventListener("submit", (evento) => {
        const fimEtapa = cronometroContainer.dataset.fimEtapa;

        if (!fimEtapa) {return;}

        const horarioFim = new Date(fimEtapa).getTime();

        if (Date.now() >= horarioFim) {
            evento.preventDefault();

            bloquearResposta();
            cronometro.textContent = "00:00";
        }});}