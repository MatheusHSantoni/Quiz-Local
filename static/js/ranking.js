const cartas = document.querySelectorAll(".carta");
const campoBusca = document.querySelector("#busca-ranking");
const dicaBusca = document.querySelector("#ranking-dica");
const botaoRevelar = document.querySelector("#btn-revelar");
const anuncio = document.querySelector("#anuncio");

const vagasPodio = {
    1: document.querySelector("#vaga-1"),
    2: document.querySelector("#vaga-2"),
    3: document.querySelector("#vaga-3")
};


/*VIRAR CARTA*/

cartas.forEach((carta) => {
    carta.addEventListener("click", () => {
        carta.classList.toggle("virada");
    });
});

function normalizarTexto(texto) {
    return texto
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .trim();
}

/*BUSCA*/

if (campoBusca) {
    campoBusca.addEventListener("input", () => {
        const termo = normalizarTexto(campoBusca.value);
        let encontrados = 0;

        cartas.forEach((carta) => {
            const nome = normalizarTexto(carta.dataset.nome);
            const corresponde = nome.includes(termo);

            if (corresponde) {
                carta.classList.remove("escondida");

                if (termo !== "") {
                    carta.classList.add("encontrada");
                } else {
                    carta.classList.remove("encontrada");
                }

                encontrados++;
            } else {
                carta.classList.add("escondida");
                carta.classList.remove("encontrada");
            }});

        if (termo === "") {
            dicaBusca.textContent = "";
            return;
        }

        if (encontrados === 0) {
            dicaBusca.textContent = "Nenhuma dupla encontrada.";
            return;
        }

        if (encontrados === 1) {
            dicaBusca.textContent = "1 dupla encontrada.";
            return;
        }

        dicaBusca.textContent = `${encontrados} duplas encontradas.`;
    });}


/* REVELAR PÓDIO */

function revelarVaga(posicao) {
    const vaga = vagasPodio[posicao];

    if (!vaga) {
        return;
    }

    const quem = vaga.querySelector(".quem");

    if (!quem) {
        return;
    }

    const nome = quem.dataset.nome;
    const pontos = quem.dataset.pontos;
    const avatar = quem.querySelector(".av");
    const nomeElemento = quem.querySelector(".nm");
    const degrauInfo = vaga.querySelector(".degrau span");

    if (avatar) {
        avatar.textContent = posicao;}

    if (nomeElemento) {
        nomeElemento.textContent = nome;}

    if (degrauInfo) {
        degrauInfo.textContent = `${pontos} pontos`;}

    vaga.classList.add("revelada");
}


/* ESPERA */

function esperar(ms) {
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });}


/* REVELAÇÃO COMPLETA */

async function revelarClassificacao() {
    if (!botaoRevelar) {
        return;}

    botaoRevelar.disabled = true;

    const cartasOrdenadas = Array.from(cartas).sort(
        (cartaA, cartaB) => {
            const posicaoA = Number(cartaA.dataset.posicao);
            const posicaoB = Number(cartaB.dataset.posicao);

            return posicaoB - posicaoA;
        });

    anuncio.textContent = "Revelando classificação...";

    for (const carta of cartasOrdenadas) {
        carta.classList.add("virada");
        await esperar(180);}

    anuncio.textContent = "Agora, o pódio!";

    await esperar(700);
    revelarVaga(3);
    await esperar(900);
    revelarVaga(2);
    await esperar(900);
    revelarVaga(1);

    anuncio.textContent = "Ranking revelado!";
    botaoRevelar.textContent = "Classificação revelada";
}


/* BOTÃO REVELAR */

if (botaoRevelar) {
    botaoRevelar.addEventListener(
        "click",
        revelarClassificacao
    );}