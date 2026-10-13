const alternativas = document.querySelectorAll('input[name="alternativa"]');

alternativas.forEach((alternativa) => {
    alternativa.addEventListener("change", () => {
        document.querySelectorAll(".op").forEach((opcao) => {
            opcao.classList.remove("sel");
        });

        alternativa.closest(".op").classList.add("sel");
    });
});