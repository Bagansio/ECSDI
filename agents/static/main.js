

document.addEventListener("DOMContentLoaded", function(){
     var tableElements = document.getElementsByClassName("purchase");
     for(var i=0;i<tableElements.length;i++){
        tableElements[i].addEventListener("click", async (event) => {

            fetch("/addcart", {
              method: "post",
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
              },

              //make sure to serialize your JSON body
              body: JSON.stringify({
                product: event.target.id
              })
            })
            .then(function(res){
                if (res.status === 200){
                    alert("AÑADIDO");
                }
            })
        });
      }
})

document.addEventListener("DOMContentLoaded", function(){
     var tableElements = document.getElementsByClassName("remove");
     for(var i=0;i<tableElements.length;i++){
        tableElements[i].addEventListener("click", async (event) => {

            fetch("/removecart", {
              method: "post",
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
              },

              //make sure to serialize your JSON body
              body: JSON.stringify({
                product: event.target.id
              })
            })
            .then(function(res){
                if (res.status === 200){
                    event.target.parentElement.parentElement.remove()
                }
            })
        });
      }
})
/*
document.addEventListener("DOMContentLoaded", function(){
     var tableElements = document.getElementsByClassName("info");
     for(var i=0;i<tableElements.length;i++){
        tableElements[i].addEventListener("click", async (event) => {

            fetch("/historialinfo", {
              method: "post",
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
              },

              //make sure to serialize your JSON body
              body: JSON.stringify({
                factura: event.target.id
              })
            })
        });
      }
})
*/



