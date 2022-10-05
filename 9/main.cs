using Modelos;

class Aula9 {

  public static void Main (string[] args){
    Aluno aluno1 = new Aluno(1);
    aluno1.cpf = "660.063.460-20";
    PaginaALuno paginaAluno = new PaginaAluno();
    Impressora.imprimir(paginaAluno.Formatar(aluno1));
    
  }
}